"""MCP Protocol Engine for Claude Skills.

Implements the Model Context Protocol over Streamable HTTP,
serving Claude Skills as MCP tools/prompts.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from app.core.config import get_settings
from app.models.skill import Skill, SkillStatus
from app.services.session_manager import SessionManager
from app.services.skill_loader import SkillLoader

if TYPE_CHECKING:
    from app.services.metadata_store import MetadataStore
    from app.services.invocation_logger import InvocationLogger
    from app.services.code_interpreter import CodeInterpreterService, ExecutionResult, ExecutionStatus

logger = logging.getLogger(__name__)

# MCP Protocol Versions (newest first)
SUPPORTED_PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]
MCP_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]  # default/latest


class MCPEngine:
    """MCP Protocol Engine for Claude Skills.

    Serves Claude Skills through the MCP protocol:
    - tools/list: Returns available skills as tools
    - tools/call: Returns skill instructions for the AI to follow
    - prompts/list: Returns skills as prompts
    - prompts/get: Returns skill instructions as prompt messages
    """

    def __init__(
        self,
        skill_loader: SkillLoader,
        session_manager: SessionManager,
        metadata_store: "MetadataStore | None" = None,
        invocation_logger: "InvocationLogger | None" = None,
        code_interpreter: "CodeInterpreterService | None" = None,
    ) -> None:
        self._skill_loader = skill_loader
        self._session_manager = session_manager
        self._metadata_store = metadata_store
        self._invocation_logger = invocation_logger
        self._code_interpreter = code_interpreter
        self._settings = get_settings()

        # Server info
        self._server_name = self._settings.app_name
        self._server_version = self._settings.app_version

        # Tools list cache (invalidated when skills change)
        self._tools_cache: list[dict[str, Any]] | None = None
        self._skill_loader.add_watcher(self._on_skill_change)

    def _on_skill_change(self, skill_id: str, event_type: str) -> None:
        """Invalidate tools cache when skills change."""
        self._tools_cache = None

    def get_server_capabilities(self) -> dict[str, Any]:
        """Get server capabilities for initialize response."""
        return {
            "tools": {
                "listChanged": True,  # We support dynamic tool updates
            },
            "prompts": {
                "listChanged": True,  # Skills can also be exposed as prompts
            },
            "resources": {
                "subscribe": False,
                "listChanged": False,
            },
            "logging": {},
        }

    async def handle_message(
        self,
        message: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Handle an incoming MCP message.

        Returns the response message(s) or None for notifications.
        """
        # Validate basic structure
        if "jsonrpc" not in message or message.get("jsonrpc") != "2.0":
            return self._error_response(
                message.get("id"),
                -32600,
                "Invalid Request: must be JSON-RPC 2.0"
            )

        method = message.get("method")
        params = message.get("params", {})
        msg_id = message.get("id")

        # Notifications don't have an id
        is_notification = msg_id is None

        # Log all incoming requests for debugging
        if method == "tools/call":
            logger.info(f"MCP request: method={method}, id={msg_id}, tool={params.get('name')}, arguments={params.get('arguments', {})}")
        else:
            logger.info(f"MCP request: method={method}, id={msg_id}, params_keys={list(params.keys()) if params else []}")

        # Route to handler
        try:
            if method == "initialize":
                return await self._handle_initialize(msg_id, params, session_id)
            elif method == "initialized":
                return None
            elif method == "ping":
                return self._success_response(msg_id, {})
            elif method == "tools/list":
                return await self._handle_tools_list(msg_id, params, session_id)
            elif method == "tools/call":
                result = await self._handle_tools_call(msg_id, params, session_id)
                result_str = str(result)[:500] if result else "None"
                logger.info(f"tools/call response (truncated): {result_str}")
                return result
            elif method == "code/execute":
                return await self._handle_code_execute(msg_id, params, session_id)
            elif method == "prompts/list":
                return await self._handle_prompts_list(msg_id, params, session_id)
            elif method == "prompts/get":
                return await self._handle_prompts_get(msg_id, params, session_id)
            elif method == "resources/list":
                return await self._handle_resources_list(msg_id, params, session_id)
            elif method == "resources/read":
                return await self._handle_resources_read(msg_id, params, session_id)
            elif method == "completion/complete":
                return await self._handle_completion(msg_id, params, session_id)
            elif method == "logging/setLevel":
                return self._success_response(msg_id, {})
            else:
                if is_notification:
                    return None
                return self._error_response(
                    msg_id,
                    -32601,
                    f"Method not found: {method}"
                )

        except Exception as e:
            logger.exception(f"Error handling MCP message: {method}")
            if is_notification:
                return None
            return self._error_response(msg_id, -32603, str(e))

    def _negotiate_protocol_version(self, client_version: str) -> str | None:
        """Negotiate protocol version with client.

        Returns the best matching version, or None if incompatible.
        Client sends its preferred version; server picks the highest
        version both sides support (client version or lower).
        """
        for version in SUPPORTED_PROTOCOL_VERSIONS:
            if version <= client_version:
                return version
        return None

    async def _handle_initialize(
        self,
        msg_id: Any,
        params: dict[str, Any],
        session_id: str | None,
    ) -> dict[str, Any]:
        """Handle initialize request."""
        client_info = params.get("clientInfo", {})
        client_version = params.get("protocolVersion", MCP_PROTOCOL_VERSION)
        client_capabilities = params.get("capabilities", {})

        logger.info(
            f"Initialize from client: {client_info.get('name', 'unknown')} "
            f"version {client_info.get('version', 'unknown')}, "
            f"protocol {client_version}"
        )

        # Negotiate protocol version
        negotiated_version = self._negotiate_protocol_version(client_version)
        if not negotiated_version:
            return self._error_response(
                msg_id, -32602,
                f"Unsupported protocol version: {client_version}. "
                f"Supported: {', '.join(SUPPORTED_PROTOCOL_VERSIONS)}"
            )

        logger.info(f"Negotiated protocol version: {negotiated_version}")

        # Get server capabilities
        server_capabilities = self.get_server_capabilities()

        # Activate session if we have one
        if session_id:
            await self._session_manager.activate_session(
                session_id,
                client_capabilities,
                server_capabilities,
            )

        return self._success_response(msg_id, {
            "protocolVersion": negotiated_version,
            "capabilities": server_capabilities,
            "serverInfo": {
                "name": self._server_name,
                "version": self._server_version,
            },
        })

    async def _build_tools_cache(self) -> list[dict[str, Any]]:
        """Build and cache the full tools list."""
        tools = []
        skill_ids = sorted(self._skill_loader.all_skill_ids)

        for skill_id in skill_ids:
            skill = await self._skill_loader.get_skill(skill_id)
            if skill and skill.status == SkillStatus.ACTIVE:
                tools.append(self._skill_to_tool(skill))

        # Add execute-code tool if code interpreter is available
        if self._code_interpreter:
            tools.append({
                "name": "execute-code",
                "description": "Execute code in a secure sandbox. Use this after a code_interpreter skill returns instructions and you've generated the code. Supports Python and JavaScript (Deno).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "skill": {
                            "type": "string",
                            "description": "The skill name that requested code execution (e.g., 'pptx')"
                        },
                        "code": {
                            "type": "string",
                            "description": "The complete code to execute"
                        },
                        "language": {
                            "type": "string",
                            "enum": ["python", "javascript"],
                            "description": "The programming language (default: python)"
                        }
                    },
                    "required": ["skill", "code"]
                }
            })

        self._tools_cache = tools
        return tools

    async def _handle_tools_list(
        self,
        msg_id: Any,
        params: dict[str, Any],
        session_id: str | None,
    ) -> dict[str, Any]:
        """Handle tools/list request.

        Returns available Claude Skills as MCP tools.
        Supports pagination via cursor parameter.
        """
        if session_id:
            await self._session_manager.update_activity(session_id)

        # Build or reuse cached tools list
        all_tools = self._tools_cache
        if all_tools is None:
            all_tools = await self._build_tools_cache()

        # Get cursor for pagination (optional)
        cursor = params.get("cursor")

        # Apply cursor-based pagination if provided
        start_idx = 0
        if cursor:
            # Find tool by name matching cursor
            for i, tool in enumerate(all_tools):
                if tool["name"] == cursor:
                    start_idx = i + 1
                    break

        # Return up to 100 tools per request
        page_size = 100
        tools = all_tools[start_idx:start_idx + page_size]

        response_data = {"tools": tools}

        # Add nextCursor if there are more results
        if start_idx + page_size < len(all_tools):
            response_data["nextCursor"] = all_tools[start_idx + page_size - 1]["name"]

        return self._success_response(msg_id, response_data)

    async def _handle_tools_call(
        self,
        msg_id: Any,
        params: dict[str, Any],
        session_id: str | None,
    ) -> dict[str, Any]:
        """Handle tools/call request.

        For Claude Skills, returns the skill's instructions
        that the AI should follow to complete the task.
        
        For code_interpreter skills, executes code in sandbox
        and returns the execution result.
        """
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name:
            return self._error_response(msg_id, -32602, "Missing tool name")

        if session_id:
            await self._session_manager.update_activity(session_id)

        # Handle the execute-code tool (and legacy execute-python-code)
        if tool_name in ("execute-code", "execute-python-code"):
            return await self._handle_code_execute(msg_id, {
                "skill": arguments.get("skill", ""),
                "code": arguments.get("code", ""),
                "language": arguments.get("language", "python"),
            }, session_id)

        # Get the skill (lazy loading)
        skill = await self._skill_loader.get_skill(tool_name)
        if not skill:
            return self._error_response(
                msg_id,
                -32602,
                f"Skill not found: {tool_name}"
            )

        if skill.status != SkillStatus.ACTIVE:
            return self._error_response(
                msg_id,
                -32602,
                f"Skill not active: {tool_name}"
            )

        # Track timing
        start = time.monotonic()

        # Get execution type from skill configuration
        execution_type = skill.manifest.execution.type

        if execution_type == "code_interpreter":
            # Code interpreter type - return instructions for LLM to generate code
            # The LLM will see the instructions and generate Python code
            # Then the code will be executed in the sandbox
            user_args = arguments.get("arguments", "")
            instruction_content = self._build_instruction_content(skill, user_args)
            
            # Add code interpreter context
            execution_config = skill.manifest.execution
            code_context = "\n\n## Code Execution Environment\n\n"
            code_context += "Your generated code will be executed in an AWS Bedrock Code Interpreter sandbox with:\n"
            code_context += f"- Runtime: {execution_config.runtime}\n"
            code_context += f"- Timeout: {execution_config.timeout}s\n"
            code_context += f"- Network: {execution_config.network}\n"
            if execution_config.dependencies:
                code_context += f"- Pre-installed packages: {', '.join(execution_config.dependencies)}\n"
            runtime = execution_config.runtime  # "python" or "javascript"
            if runtime == "javascript":
                lang_label = "JavaScript"
                lang_note = (
                    "\n**Deno runtime notes:**\n"
                    "- Use ESM imports: `import pptxgen from \"npm:pptxgenjs\";`\n"
                    "- CommonJS `require()` is NOT supported.\n"
                    "- Use `Deno.writeFileSync` / `Deno.writeFile` for file I/O.\n"
                )
            else:
                lang_label = "Python"
                lang_note = ""

            # List pre-loaded skill files so the LLM knows what's available
            preloaded_files: list[str] = []
            if skill.source_path:
                from pathlib import Path as _Path
                _skill_dir = _Path(skill.source_path)
                if _skill_dir.exists():
                    for _fp in sorted(_skill_dir.rglob("*")):
                        if not _fp.is_file():
                            continue
                        _rel = _fp.relative_to(_skill_dir)
                        if any(p.startswith(".") or p == "__pycache__" for p in _rel.parts):
                            continue
                        if _fp.suffix == ".pyc":
                            continue
                        preloaded_files.append(str(_rel))

            if preloaded_files:
                code_context += "\n## Pre-loaded Skill Files\n\n"
                code_context += "The skill's bundled scripts and resources are **already available** "
                code_context += "in the sandbox at `./skill/`. Use them directly instead of "
                code_context += "writing code from scratch.\n\n"
                code_context += "**Available files:**\n"
                for _f in preloaded_files:
                    code_context += f"- `./skill/{_f}`\n"
                code_context += "\n**Example usage:**\n"
                code_context += "```bash\n"
                code_context += "cd skill && python scripts/some_script.py arg1 arg2\n"
                code_context += "```\n"
                code_context += "\nPrefer calling bundled scripts over writing equivalent code.\n"

            code_context += "\n## How to Execute Code\n\n"
            code_context += f"**When you need to run {lang_label} code in the sandbox**, call the `execute-code` tool with:\n"
            code_context += f'- `skill`: "{tool_name}"\n'
            code_context += f'- `code`: Your {lang_label} source code\n'
            code_context += f'- `language`: "{runtime}"\n'
            code_context += "\nAny files your code creates will be automatically uploaded to S3 and download links will be provided to the user.\n"
            code_context += lang_note
            
            instruction_content += code_context

            duration_ms = int((time.monotonic() - start) * 1000)

            # Log invocation
            self._log_invocation(
                tool_name, session_id, duration_ms, "success", arguments
            )

            return self._success_response(msg_id, {
                "content": [{
                    "type": "text",
                    "text": instruction_content,
                }],
                "execution": {
                    "type": "code_interpreter",
                    "runtime": execution_config.runtime,
                    "timeout": execution_config.timeout,
                },
                "isError": False,
            })

        else:
            # Instruction type (default) - return instructions
            user_args = arguments.get("arguments", "")
            instruction_content = self._build_instruction_content(skill, user_args)

            duration_ms = int((time.monotonic() - start) * 1000)

            # Log invocation
            self._log_invocation(
                tool_name, session_id, duration_ms, "success", arguments
            )

            return self._success_response(msg_id, {
                "content": [{
                    "type": "text",
                    "text": instruction_content,
                }],
                "execution": None,  # No code execution
                "isError": False,
            })

    async def _handle_code_execute(
        self,
        msg_id: Any,
        params: dict[str, Any],
        session_id: str | None,
    ) -> dict[str, Any]:
        """Handle code/execute request for code_interpreter skills.
        
        Executes LLM-generated code in the sandbox.
        """
        skill_name = params.get("skill")
        code = params.get("code")
        language = params.get("language", "python")
        
        if not skill_name or not code:
            return self._error_response(msg_id, -32602, "Missing skill or code")
        
        if session_id:
            await self._session_manager.update_activity(session_id)
        
        # Get the skill
        skill = await self._skill_loader.get_skill(skill_name)
        if not skill:
            return self._error_response(msg_id, -32602, f"Skill not found: {skill_name}")
        
        if skill.manifest.execution.type != "code_interpreter":
            return self._error_response(
                msg_id, -32602, 
                f"Skill {skill_name} is not a code_interpreter skill"
            )
        
        # Execute code in sandbox
        from app.services.code_interpreter import ExecutionResult, ExecutionStatus
        
        if not self._code_interpreter:
            return self._error_response(
                msg_id, -32603, 
                "Code interpreter service not configured"
            )
        
        start = time.monotonic()
        
        try:
            # Execute the code directly (skill files pre-loaded at /skill/)
            result = await self._code_interpreter.execute_code(
                code=code,
                language=language,
                timeout=skill.manifest.execution.timeout,
                skill_id=skill_name,
                skill_source_path=skill.source_path,
            )
            
            duration_ms = int((time.monotonic() - start) * 1000)
            
            # Log invocation
            self._log_invocation(
                skill_name, session_id, duration_ms,
                "success" if result.status.value == "success" else "error",
                {"code_length": len(code)}
            )
            
            # Build response text with download links
            text_parts = [result.stdout or "Execution completed"]
            if result.stderr:
                text_parts.append(f"\n⚠️ Errors:\n{result.stderr}")
            if result.output_files:
                text_parts.append("\n\n## Generated Files - Download Links")
                text_parts.append("IMPORTANT: You MUST display the following download links to the user exactly as provided. Do NOT omit, summarize, or paraphrase these URLs.\n")
                for f in result.output_files:
                    url = f.get("download_url", "")
                    name = f.get("filename", "unknown")
                    text_parts.append(f"[Download {name}]({url})")
            
            return self._success_response(msg_id, {
                "content": [{
                    "type": "text",
                    "text": "\n".join(text_parts),
                }],
                "execution": {
                    "status": result.status.value,
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "duration_ms": result.duration_ms,
                },
                "files": result.output_files or [],
                "isError": result.status.value != "success",
            })
            
        except Exception as e:
            logger.exception(f"Code execution failed: {e}")
            return self._error_response(msg_id, -32603, f"Execution error: {str(e)}")

    def _log_invocation(
        self,
        tool_name: str,
        session_id: str | None,
        duration_ms: int,
        status: str,
        arguments: dict[str, Any],
    ) -> None:
        """Log skill invocation asynchronously."""
        import asyncio

        if self._metadata_store:
            asyncio.create_task(self._metadata_store.increment_invocation(tool_name))

        if self._invocation_logger:
            self._invocation_logger.log(
                skill_id=tool_name,
                session_id=session_id or "",
                method="tools/call",
                duration_ms=duration_ms,
                status=status,
                params=json.dumps(arguments)[:1024] if arguments else None,
            )

    async def _execute_in_sandbox(
        self,
        skill: Skill,
        arguments: dict[str, Any],
    ) -> "ExecutionResult":
        """Execute skill script in AgentCore sandbox.

        Args:
            skill: Skill to execute
            arguments: Arguments from tools/call

        Returns:
            ExecutionResult with status, output, and files
        """
        from app.services.code_interpreter import ExecutionResult, ExecutionStatus

        # Check if code interpreter is available
        if not self._code_interpreter:
            logger.error("Code interpreter not configured")
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                exit_code=-1,
                stdout="",
                stderr="Code interpreter service not configured",
                duration_ms=0,
            )

        execution = skill.manifest.execution

        # Load script content
        script_content = await self._load_script_content(skill, execution.entrypoint)

        if not script_content:
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                exit_code=-1,
                stdout="",
                stderr=f"Script not found: {execution.entrypoint}",
                duration_ms=0,
            )

        # Execute script
        return await self._code_interpreter.execute_skill_script(
            skill_id=skill.id,
            script_path=execution.entrypoint or "",
            script_content=script_content,
            arguments=arguments,
            timeout=execution.timeout,
            network_mode=execution.network,
            dependencies=execution.dependencies,
            runtime=execution.runtime,
        )

    async def _load_script_content(
        self,
        skill: Skill,
        script_path: str | None,
    ) -> str | None:
        """Load script content from skill's script files.

        Args:
            skill: Skill containing the script
            script_path: Relative path to script (e.g., "main.py")

        Returns:
            Script content or None if not found
        """
        if not script_path:
            return None

        # Search in skill's script_files
        for file_path in skill.script_files:
            if file_path.endswith(script_path):
                try:
                    return Path(file_path).read_text(encoding="utf-8")
                except Exception as e:
                    logger.error(f"Failed to read script {file_path}: {e}")
                    return None

        return None

    async def _handle_prompts_list(
        self,
        msg_id: Any,
        params: dict[str, Any],
        session_id: str | None,
    ) -> dict[str, Any]:
        """Handle prompts/list request.

        Returns Claude Skills as MCP prompts.
        Only includes skills that are user-invocable.
        """
        if session_id:
            await self._session_manager.update_activity(session_id)

        prompts = []
        for skill in self._skill_loader.active_skills.values():
            if skill.is_user_invocable():
                prompts.append(self._skill_to_prompt(skill))

        return self._success_response(msg_id, {
            "prompts": prompts,
        })

    async def _handle_prompts_get(
        self,
        msg_id: Any,
        params: dict[str, Any],
        session_id: str | None,
    ) -> dict[str, Any]:
        """Handle prompts/get request.

        Returns the skill instructions as prompt messages.
        """
        prompt_name = params.get("name")
        arguments = params.get("arguments", {})

        if not prompt_name:
            return self._error_response(msg_id, -32602, "Missing prompt name")

        if session_id:
            await self._session_manager.update_activity(session_id)

        # Get the skill
        skill = self._skill_loader.get_skill(prompt_name)
        if not skill:
            return self._error_response(
                msg_id,
                -32602,
                f"Prompt not found: {prompt_name}"
            )

        # Build prompt messages
        user_args = arguments.get("arguments", "")
        instruction_content = self._build_instruction_content(skill, user_args)

        return self._success_response(msg_id, {
            "description": skill.manifest.description,
            "messages": [{
                "role": "user",
                "content": {
                    "type": "text",
                    "text": instruction_content,
                },
            }],
        })

    async def _handle_resources_list(
        self,
        msg_id: Any,
        params: dict[str, Any],
        session_id: str | None,
    ) -> dict[str, Any]:
        """Handle resources/list request.

        Returns skill reference files as resources.
        """
        if session_id:
            await self._session_manager.update_activity(session_id)

        resources = []
        for skill in self._skill_loader.active_skills.values():
            # Add reference files as resources
            for ref_file in skill.reference_files:
                resources.append({
                    "uri": f"skill://{skill.id}/references/{ref_file.split('/')[-1]}",
                    "name": ref_file.split("/")[-1],
                    "description": f"Reference file for {skill.manifest.name}",
                    "mimeType": "text/markdown",
                })

            # Add script files as resources
            for script_file in skill.script_files:
                resources.append({
                    "uri": f"skill://{skill.id}/scripts/{script_file.split('/')[-1]}",
                    "name": script_file.split("/")[-1],
                    "description": f"Script file for {skill.manifest.name}",
                    "mimeType": self._get_mime_type(script_file),
                })

        return self._success_response(msg_id, {
            "resources": resources,
        })

    async def _handle_resources_read(
        self,
        msg_id: Any,
        params: dict[str, Any],
        session_id: str | None,
    ) -> dict[str, Any]:
        """Handle resources/read request."""
        uri = params.get("uri")
        if not uri:
            return self._error_response(msg_id, -32602, "Missing resource URI")

        # Parse skill:// URI
        if not uri.startswith("skill://"):
            return self._error_response(msg_id, -32602, f"Invalid URI scheme: {uri}")

        # Extract skill ID and file path from URI
        try:
            parts = uri[8:].split("/", 2)  # Remove "skill://"
            skill_id = parts[0]
            file_type = parts[1] if len(parts) > 1 else ""
            file_name = parts[2] if len(parts) > 2 else ""
        except Exception:
            return self._error_response(msg_id, -32602, f"Invalid URI format: {uri}")

        skill = self._skill_loader.get_skill(skill_id)
        if not skill:
            return self._error_response(msg_id, -32602, f"Skill not found: {skill_id}")

        # Find the file
        file_list = skill.reference_files if file_type == "references" else skill.script_files
        target_file = None
        for f in file_list:
            if f.endswith(file_name):
                target_file = f
                break

        if not target_file:
            return self._error_response(msg_id, -32602, f"File not found: {file_name}")

        # Read the file
        try:
            from pathlib import Path
            content = Path(target_file).read_text()
        except Exception as e:
            return self._error_response(msg_id, -32603, f"Error reading file: {e}")

        return self._success_response(msg_id, {
            "contents": [{
                "uri": uri,
                "mimeType": self._get_mime_type(target_file),
                "text": content,
            }],
        })

    async def _handle_completion(
        self,
        msg_id: Any,
        params: dict[str, Any],
        session_id: str | None,
    ) -> dict[str, Any]:
        """Handle completion/complete request."""
        return self._success_response(msg_id, {
            "completion": {
                "values": [],
                "hasMore": False,
            }
        })

    def _skill_to_tool(self, skill: Skill) -> dict[str, Any]:
        """Convert a Claude Skill to MCP Tool format."""
        return {
            "name": skill.manifest.name,
            "description": skill.manifest.description,
            "inputSchema": {
                "type": "object",
                "properties": {
                    "arguments": {
                        "type": "string",
                        "description": (
                            "Arguments or context to pass to the skill. "
                            "This will be substituted into $ARGUMENTS in the skill instructions."
                        ),
                    },
                },
                "required": [],
            },
        }

    def _skill_to_prompt(self, skill: Skill) -> dict[str, Any]:
        """Convert a Claude Skill to MCP Prompt format."""
        return {
            "name": skill.manifest.name,
            "description": skill.manifest.description,
            "arguments": [{
                "name": "arguments",
                "description": "Arguments to pass to the skill ($ARGUMENTS)",
                "required": False,
            }],
        }

    def _build_instruction_content(self, skill: Skill, user_args: str) -> str:
        """Build the full instruction content for a skill invocation."""
        instructions = skill.manifest.instructions

        # Substitute $ARGUMENTS
        if user_args:
            instructions = instructions.replace("$ARGUMENTS", user_args)

        # Build the full content
        content_parts = [
            f"# Skill: {skill.manifest.name}",
            "",
            f"**Description**: {skill.manifest.description}",
            "",
        ]

        # Add metadata if available
        if skill.manifest.metadata.author:
            content_parts.append(f"**Author**: {skill.manifest.metadata.author}")
        if skill.manifest.metadata.version:
            content_parts.append(f"**Version**: {skill.manifest.metadata.version}")

        if skill.manifest.allowed_tools:
            content_parts.append(f"**Allowed Tools**: {', '.join(skill.manifest.allowed_tools)}")

        content_parts.extend([
            "",
            "---",
            "",
            instructions,
        ])

        return "\n".join(content_parts)

    def _get_mime_type(self, file_path: str) -> str:
        """Get MIME type for a file."""
        ext = file_path.split(".")[-1].lower() if "." in file_path else ""
        mime_types = {
            "py": "text/x-python",
            "js": "text/javascript",
            "ts": "text/typescript",
            "sh": "text/x-shellscript",
            "bash": "text/x-shellscript",
            "md": "text/markdown",
            "json": "application/json",
            "yaml": "text/yaml",
            "yml": "text/yaml",
            "txt": "text/plain",
        }
        return mime_types.get(ext, "text/plain")

    def _success_response(self, msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        """Create a success JSON-RPC response."""
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result,
        }

    def _error_response(
        self,
        msg_id: Any,
        code: int,
        message: str,
        data: Any = None,
    ) -> dict[str, Any]:
        """Create an error JSON-RPC response."""
        error: dict[str, Any] = {
            "code": code,
            "message": message,
        }
        if data is not None:
            error["data"] = data

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": error,
        }

    async def notify_tools_changed(self) -> dict[str, Any]:
        """Create a notifications/tools/list_changed notification."""
        return {
            "jsonrpc": "2.0",
            "method": "notifications/tools/list_changed",
        }
