"""MCP Protocol Engine for Claude Skills.

Implements the Model Context Protocol over Streamable HTTP,
serving Claude Skills as MCP tools/prompts.
"""

import logging
from datetime import datetime
from typing import Any

from app.core.config import get_settings
from app.models.skill import Skill, SkillStatus
from app.services.session_manager import SessionManager
from app.services.skill_loader import SkillLoader

logger = logging.getLogger(__name__)

# MCP Protocol Version
MCP_PROTOCOL_VERSION = "2025-11-25"


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
    ) -> None:
        self._skill_loader = skill_loader
        self._session_manager = session_manager
        self._settings = get_settings()

        # Server info
        self._server_name = self._settings.app_name
        self._server_version = self._settings.app_version

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
                return await self._handle_tools_call(msg_id, params, session_id)
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

    async def _handle_initialize(
        self,
        msg_id: Any,
        params: dict[str, Any],
        session_id: str | None,
    ) -> dict[str, Any]:
        """Handle initialize request."""
        client_info = params.get("clientInfo", {})
        protocol_version = params.get("protocolVersion", MCP_PROTOCOL_VERSION)
        client_capabilities = params.get("capabilities", {})

        logger.info(
            f"Initialize from client: {client_info.get('name', 'unknown')} "
            f"version {client_info.get('version', 'unknown')}"
        )

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
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": server_capabilities,
            "serverInfo": {
                "name": self._server_name,
                "version": self._server_version,
            },
        })

    async def _handle_tools_list(
        self,
        msg_id: Any,
        params: dict[str, Any],
        session_id: str | None,
    ) -> dict[str, Any]:
        """Handle tools/list request.

        Returns available Claude Skills as MCP tools.
        """
        if session_id:
            await self._session_manager.update_activity(session_id)

        tools = []
        for skill in self._skill_loader.active_skills.values():
            tools.append(self._skill_to_tool(skill))

        return self._success_response(msg_id, {
            "tools": tools,
        })

    async def _handle_tools_call(
        self,
        msg_id: Any,
        params: dict[str, Any],
        session_id: str | None,
    ) -> dict[str, Any]:
        """Handle tools/call request.

        For Claude Skills, returns the skill's instructions
        that the AI should follow to complete the task.
        """
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name:
            return self._error_response(msg_id, -32602, "Missing tool name")

        if session_id:
            await self._session_manager.update_activity(session_id)

        # Get the skill
        skill = self._skill_loader.get_skill(tool_name)
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

        # Update invocation stats
        skill.invocation_count += 1
        skill.last_invoked_at = datetime.utcnow()

        # Build the response with skill instructions
        user_args = arguments.get("arguments", "")

        # Construct the full instruction content
        instruction_content = self._build_instruction_content(skill, user_args)

        return self._success_response(msg_id, {
            "content": [{
                "type": "text",
                "text": instruction_content,
            }],
            "isError": False,
        })

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
