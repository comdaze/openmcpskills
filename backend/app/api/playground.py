"""Playground API endpoints for testing MCP skills with AI models."""

import asyncio
import logging
import re
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import boto3
from botocore.config import Config
import json
import httpx

from app.core.config import get_settings
from app.api.deps import INTERNAL_BYPASS_TOKEN

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/playground", tags=["playground"])

# Cache for MCP tools
_tools_cache = {}
_cache_timestamp = {}
CACHE_TTL = 300  # 5 minutes

# Max output tokens per model (set to each model's maximum)
MODEL_MAX_TOKENS = {
    "claude-opus-4-6": 128000,   # Opus 4.6: 128K (Bedrock limit)
    "claude-opus-4-5": 65536,    # Opus 4.5: 64K
    "claude-sonnet-4-5": 65536,  # Sonnet 4.5: 64K
    "claude-haiku-4-5": 65536,   # Haiku 4.5: 64K
}


class Message(BaseModel):
    role: str
    content: Any  # str or list of content blocks


class ChatRequest(BaseModel):
    # Legacy format
    message: Optional[str] = None
    history: List[Message] = []
    # New format (from playground-runtime.ts)
    messages: Optional[List[Message]] = None
    model: str = "claude-opus-4-5"
    useMcpServer: Optional[bool] = None
    use_mcp_server: Optional[bool] = None
    mcpServerUrl: Optional[str] = None
    mcp_server_url: Optional[str] = None
    bedrockEndpoint: Optional[str] = None
    bedrock_endpoint: Optional[str] = None
    bedrockApiKey: Optional[str] = None
    bedrock_api_key: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    content: List[Dict[str, Any]] = []
    toolCalls: List[Dict[str, Any]] = []


async def get_mcp_tools(mcp_url: str) -> List[Dict[str, Any]]:
    """Fetch available tools from MCP server with caching."""
    import time

    # Check cache
    now = time.time()
    if mcp_url in _tools_cache:
        if now - _cache_timestamp.get(mcp_url, 0) < CACHE_TTL:
            return _tools_cache[mcp_url]

    try:
        # Use localhost to bypass auth when calling ourselves
        settings = get_settings()
        local_url = "http://127.0.0.1:8000/mcp"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                local_url,
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                headers={"X-Internal-Token": INTERNAL_BYPASS_TOKEN},
                timeout=10.0
            )
            if response.status_code == 200:
                data = response.json()
                tools = data.get("result", {}).get("tools", [])
                # Convert MCP tools to Bedrock tool format
                bedrock_tools = []
                for tool in tools:
                    bedrock_tools.append({
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "input_schema": tool.get("inputSchema", {"type": "object", "properties": {}})
                    })
                
                # Update cache
                _tools_cache[mcp_url] = bedrock_tools
                _cache_timestamp[mcp_url] = now
                
                return bedrock_tools
    except Exception as e:
        logger.error(f"Failed to fetch MCP tools: {e}")
    return []


async def call_mcp_tool(mcp_url: str, tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Call an MCP tool and return the result."""
    try:
        local_url = "http://127.0.0.1:8000/mcp"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                local_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": tool_input
                    }
                },
                headers={"X-Internal-Token": INTERNAL_BYPASS_TOKEN},
                timeout=30.0
            )
            if response.status_code == 200:
                data = response.json()
                result = data.get("result", {})
                
                # Check if this is a code_interpreter skill that returned instructions
                execution_info = result.get("execution", {})
                if execution_info and execution_info.get("type") == "code_interpreter":
                    # This is a code_interpreter skill, return instructions to LLM
                    # LLM should generate code, which will be handled in the next iteration
                    content = result.get("content", [])
                    if content and len(content) > 0:
                        return content[0].get("text", "Tool executed successfully")
                
                # Regular tool or execution result
                content = result.get("content", [])
                if content and len(content) > 0:
                    return content[0].get("text", "Tool executed successfully")
    except Exception as e:
        logger.error(f"Failed to call MCP tool {tool_name}: {e}")
        return f"Error calling tool: {str(e)}"
    return "Tool execution failed"


def _normalize_code_for_execution(code: str) -> str:
    """Fix common Unicode issues in LLM-generated code before execution.

    Handles two issues:
    1. Smart/curly quotes in CJK text that break Python string syntax.
    2. UTF-16 surrogate pair escape sequences (e.g., \\ud83c\\udfa4 for emojis)
       that cause UnicodeEncodeError in lxml/python-pptx.
    """
    # 1. Replace raw smart quote characters with escape sequences
    smart_quotes = {
        '\u201c': '\\u201c',  # Left double quotation mark
        '\u201d': '\\u201d',  # Right double quotation mark
        '\u2018': '\\u2018',  # Left single quotation mark
        '\u2019': '\\u2019',  # Right single quotation mark
    }
    for old, new in smart_quotes.items():
        code = code.replace(old, new)

    # 2. Fix surrogate pair escape sequences: \uD83C\uDFA4 -> \U0001F3A4
    def _replace_surrogate_pair(match: re.Match) -> str:
        high = int(match.group(1), 16)
        low = int(match.group(2), 16)
        code_point = ((high - 0xD800) << 10) + (low - 0xDC00) + 0x10000
        return f'\\U{code_point:08X}'

    # High surrogate: D800-DBFF, Low surrogate: DC00-DFFF
    code = re.sub(
        r'\\u([dD][89aAbB][0-9a-fA-F]{2})\\u([dD][cCdDeEfF][0-9a-fA-F]{2})',
        _replace_surrogate_pair,
        code,
    )

    return code


async def execute_code_in_sandbox(mcp_url: str, skill_name: str, code: str, language: str = "python") -> dict:
    """Execute code in sandbox via code/execute method.

    Returns a dict with 'text' and optionally 'execution' and 'files'.
    """
    try:
        # Normalize Unicode issues (smart quotes, surrogate pairs) in LLM-generated code
        code = _normalize_code_for_execution(code)
        logger.info(f"Executing code for skill: {skill_name}, code length: {len(code)}")
        local_url = "http://127.0.0.1:8000/mcp"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                local_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "code/execute",
                    "params": {
                        "skill": skill_name,
                        "code": code,
                        "language": language
                    }
                },
                headers={"X-Internal-Token": INTERNAL_BYPASS_TOKEN},
                timeout=300.0  # 5 minutes for code execution
            )
            logger.info(f"Code execution response status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Code execution response: {data}")

                # Check for JSON-RPC error
                if "error" in data:
                    err = data["error"]
                    err_msg = err.get("message", "Unknown error") if isinstance(err, dict) else str(err)
                    logger.error(f"Code execution RPC error: {err_msg}")
                    return {"text": f"Error: {err_msg}"}

                result = data.get("result", {})
                content = result.get("content", [])
                text = content[0].get("text", "Code executed") if content else "Code executed"

                return {
                    "text": text,
                    "execution": result.get("execution"),
                    "files": result.get("files", [])
                }
            else:
                logger.error(f"Code execution failed with status {response.status_code}: {response.text}")
                return {"text": f"Code execution failed: HTTP {response.status_code}"}
    except Exception as e:
        logger.error(f"Failed to execute code: {e}", exc_info=True)
        return {"text": f"Error executing code: {str(e)}"}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Handle chat requests with optional MCP server integration."""
    try:
        settings = get_settings()
        
        # Get model ID from settings
        model_ids = {
            "claude-opus-4-6": settings.claude_opus_4_6_model_id,
            "claude-opus-4-5": settings.claude_opus_model_id,
            "claude-sonnet-4-5": settings.claude_sonnet_model_id,
            "claude-haiku-4-5": settings.claude_haiku_model_id,
        }
        
        model_id = model_ids.get(request.model)
        if not model_id:
            raise HTTPException(status_code=400, detail=f"Invalid model: {request.model}")

        # Normalize field names (support both camelCase and snake_case)
        use_mcp = request.useMcpServer if request.useMcpServer is not None else request.use_mcp_server
        if use_mcp is None:
            use_mcp = True
        mcp_url = request.mcpServerUrl or request.mcp_server_url or settings.mcp_server_url
        bedrock_endpoint = request.bedrockEndpoint or request.bedrock_endpoint or settings.bedrock_endpoint

        # Initialize Bedrock client with extended read timeout (Opus can be slow)
        bedrock_config = Config(read_timeout=300, retries={'max_attempts': 0})
        client_kwargs = {"region_name": settings.aws_region, "config": bedrock_config}
        if bedrock_endpoint:
            client_kwargs["endpoint_url"] = bedrock_endpoint

        bedrock = boto3.client("bedrock-runtime", **client_kwargs)

        # Build messages - support both old and new format
        messages = []
        if request.messages:
            # New format: messages array with content blocks
            for msg in request.messages:
                if isinstance(msg.content, str):
                    messages.append({"role": msg.role, "content": msg.content})
                elif isinstance(msg.content, list):
                    # Check if it's a simple text-only message
                    text_parts = []
                    has_non_text = False
                    for block in msg.content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif isinstance(block, str):
                            text_parts.append(block)
                        else:
                            has_non_text = True
                            break

                    if not has_non_text and text_parts:
                        # Simple text message — send as string (Bedrock prefers this)
                        messages.append({"role": msg.role, "content": "\n".join(text_parts)})
                    else:
                        # Complex message with tool_use/tool_result blocks
                        # invoke_model uses Anthropic Messages API format — pass blocks as-is
                        messages.append({"role": msg.role, "content": msg.content})
                else:
                    messages.append({"role": msg.role, "content": str(msg.content)})
        else:
            # Legacy format: history + message
            for msg in request.history:
                messages.append({"role": msg.role, "content": msg.content if isinstance(msg.content, str) else str(msg.content)})
            if request.message:
                messages.append({"role": "user", "content": request.message})

        # Prepare request body
        system_prompt = (
            "When generating Python code, ALWAYS use straight ASCII quotes (' or \") for "
            "string delimiters. NEVER use Unicode smart/curly quotes (\u201c \u201d \u2018 \u2019) "
            "anywhere in Python source code. When Chinese or CJK text contains quotation marks, "
            "use corner brackets (\u300c\u300d) or escaped Unicode (\\u201c \\u201d) instead of raw "
            "smart quote characters. Always use triple-quoted strings (\"\"\"...\"\"\") for "
            "multi-line text or text containing mixed quote characters."
        )
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": MODEL_MAX_TOKENS.get(request.model, 65536),
            "system": system_prompt,
            "messages": messages,
        }

        # Add MCP tools if enabled
        tools = []
        if use_mcp and mcp_url:
            tools = await get_mcp_tools(mcp_url)
            if tools:
                body["tools"] = tools
                logger.info(f"Loaded {len(tools)} tools from MCP server")

        # Invoke model (may need multiple rounds for tool use)
        max_iterations = 15
        all_tool_calls = []
        
        for iteration in range(max_iterations):
            response = bedrock.invoke_model(
                modelId=model_id,
                body=json.dumps(body)
            )

            response_body = json.loads(response["body"].read())
            stop_reason = response_body.get("stop_reason")
            
            # If no tool use, return the response
            if stop_reason != "tool_use":
                raw_content = response_body.get("content", [])
                if raw_content:
                    assistant_message = raw_content[0].get("text", "")
                else:
                    assistant_message = "Sorry, I couldn't generate a response."
                return ChatResponse(
                    response=assistant_message,
                    content=raw_content,
                    toolCalls=all_tool_calls,
                )
            
            # Handle tool use
            content_blocks = response_body.get("content", [])
            tool_results = []
            
            for block in content_blocks:
                if block.get("type") == "tool_use":
                    tool_name = block.get("name")
                    tool_input = block.get("input", {})
                    tool_use_id = block.get("id")
                    
                    logger.info(f"Calling tool: {tool_name}")
                    result = await call_mcp_tool(mcp_url, tool_name, tool_input)
                    
                    # Record tool call
                    all_tool_calls.append({
                        "name": tool_name,
                        "input": tool_input,
                        "result": result
                    })
                    
                    tool_results.append({
                        "toolResult": {
                            "toolUseId": tool_use_id,
                            "content": [{"text": result}],
                        }
                    })
            
            # Add assistant message and tool results to conversation
            # invoke_model uses Anthropic Messages API format (with "type" field)
            messages.append({"role": "assistant", "content": content_blocks})
            messages.append({"role": "user", "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tr["toolResult"]["toolUseId"],
                    "content": tr["toolResult"]["content"][0]["text"],
                }
                for tr in tool_results
            ]})
            body["messages"] = messages

        # If we hit max iterations, return last response
        return ChatResponse(
            response="Maximum tool use iterations reached.",
            content=[{"type": "text", "text": "Maximum tool use iterations reached."}],
            toolCalls=all_tool_calls,
        )

    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/chat-ws")
async def chat_websocket(websocket: WebSocket):
    """WebSocket endpoint for streaming chat responses."""
    await websocket.accept()
    
    try:
        # Receive initial message
        data = await websocket.receive_json()
        model = data.get("model", "claude-opus-4-5")
        use_mcp = data.get("useMcpServer", True)
        mcp_url = data.get("mcpServerUrl")

        settings = get_settings()

        # Get model ID
        model_ids = {
            "claude-opus-4-6": settings.claude_opus_4_6_model_id,
            "claude-opus-4-5": settings.claude_opus_model_id,
            "claude-sonnet-4-5": settings.claude_sonnet_model_id,
            "claude-haiku-4-5": settings.claude_haiku_model_id,
        }

        model_id = model_ids.get(model)
        if not model_id:
            await websocket.send_json({"type": "error", "message": f"Invalid model: {model}"})
            await websocket.close()
            return

        mcp_url = mcp_url or data.get("mcpServerUrl") or settings.mcp_server_url
        bedrock_endpoint = data.get("bedrockEndpoint") or settings.bedrock_endpoint

        # Initialize Bedrock client with extended read timeout for streaming
        bedrock_config = Config(read_timeout=300, retries={'max_attempts': 0})
        client_kwargs = {"region_name": settings.aws_region, "config": bedrock_config}
        if bedrock_endpoint:
            client_kwargs["endpoint_url"] = bedrock_endpoint

        bedrock = boto3.client("bedrock-runtime", **client_kwargs)

        # Build messages — support both new format (messages array) and legacy (message + history)
        messages = []
        if data.get("messages"):
            for msg in data["messages"]:
                content = msg.get("content")
                if isinstance(content, str):
                    messages.append({"role": msg["role"], "content": content})
                elif isinstance(content, list):
                    text_parts = []
                    has_non_text = False
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif isinstance(block, str):
                            text_parts.append(block)
                        else:
                            has_non_text = True
                            break
                    if not has_non_text and text_parts:
                        messages.append({"role": msg["role"], "content": "\n".join(text_parts)})
                    else:
                        messages.append({"role": msg["role"], "content": content})
                else:
                    messages.append({"role": msg["role"], "content": str(content)})
        else:
            # Legacy format: message + history
            for msg in data.get("history", []):
                messages.append({"role": msg.get("role"), "content": msg.get("content")})
            if data.get("message"):
                messages.append({"role": "user", "content": data["message"]})

        # Prepare request body
        system_prompt = (
            "When generating Python code, ALWAYS use straight ASCII quotes (' or \") for "
            "string delimiters. NEVER use Unicode smart/curly quotes (\u201c \u201d \u2018 \u2019) "
            "anywhere in Python source code. When Chinese or CJK text contains quotation marks, "
            "use corner brackets (\u300c\u300d) or escaped Unicode (\\u201c \\u201d) instead of raw "
            "smart quote characters. Always use triple-quoted strings (\"\"\"...\"\"\") for "
            "multi-line text or text containing mixed quote characters."
        )
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": MODEL_MAX_TOKENS.get(model, 65536),
            "system": system_prompt,
            "messages": messages,
        }

        # Add MCP tools if enabled
        tools = []
        if use_mcp and mcp_url:
            tools = await get_mcp_tools(mcp_url)
            if tools:
                body["tools"] = tools
                await websocket.send_json({"type": "status", "message": f"Loaded {len(tools)} tools"})

        # Invoke model (may need multiple rounds for tool use)
        max_iterations = 15
        all_tool_calls = []

        for iteration in range(max_iterations):
            # Use streaming API
            response = await asyncio.to_thread(
                bedrock.invoke_model_with_response_stream,
                modelId=model_id,
                body=json.dumps(body)
            )

            # Read stream events one-by-one in executor to avoid blocking the event loop.
            # Each next() call runs in a thread; the event loop stays free for WebSocket I/O.
            _STREAM_END = object()
            body_iter = iter(response['body'])

            def _next_event():
                try:
                    return next(body_iter)
                except StopIteration:
                    return _STREAM_END
                except Exception as e:
                    return e

            # Process stream events asynchronously
            content_blocks = []
            current_text = ""
            stop_reason = None
            tool_input_buffers = {}  # Buffer for accumulating tool inputs
            event_count = 0

            while True:
                raw_event = await asyncio.get_event_loop().run_in_executor(None, _next_event)
                if raw_event is _STREAM_END:
                    logger.info(f"Stream ended normally after {event_count} events")
                    break
                if isinstance(raw_event, Exception):
                    logger.error(f"Bedrock stream error after {event_count} events: {raw_event}")
                    break

                event_count += 1
                chunk = json.loads(raw_event['chunk']['bytes'])

                if chunk['type'] == 'content_block_start':
                    block = chunk['content_block']
                    block_index_start = chunk.get('index', len(content_blocks))
                    logger.info(f"content_block_start: type={block['type']}, index={block_index_start}")
                    if block['type'] == 'text':
                        current_text = ""
                    elif block['type'] == 'tool_use':
                        # Initialize input buffer for this tool
                        tool_input_buffers[block_index_start] = ""
                    content_blocks.append(block)

                elif chunk['type'] == 'content_block_delta':
                    delta = chunk['delta']
                    block_index = chunk.get('index', len(content_blocks) - 1)

                    if delta['type'] == 'text_delta':
                        current_text += delta['text']
                        # Send text chunk to client
                        logger.debug(f"Sending text_delta: {delta['text'][:50]}")
                        await websocket.send_json({
                            "type": "text_delta",
                            "text": delta['text']
                        })
                    elif delta['type'] == 'input_json_delta':
                        # Accumulate tool input JSON
                        partial = delta.get('partial_json', '')
                        if block_index in tool_input_buffers:
                            tool_input_buffers[block_index] += partial
                        else:
                            logger.error(f"No buffer for block_index={block_index}!")

                elif chunk['type'] == 'content_block_stop':
                    # Update the text block with complete text
                    block_index = chunk.get('index', len(content_blocks) - 1)
                    if content_blocks and content_blocks[block_index].get('type') == 'text':
                        content_blocks[block_index]['text'] = current_text
                    elif content_blocks and content_blocks[block_index].get('type') == 'tool_use':
                        # Parse accumulated tool input JSON
                        if block_index in tool_input_buffers:
                            try:
                                tool_input = json.loads(tool_input_buffers[block_index])
                                content_blocks[block_index]['input'] = tool_input
                                logger.info(f"Parsed tool input: {list(tool_input.keys())}")
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse tool input JSON: {e}")
                                content_blocks[block_index]['input'] = {}

                elif chunk['type'] == 'message_delta':
                    stop_reason = chunk.get('delta', {}).get('stop_reason')
                    logger.info(f"message_delta: stop_reason={stop_reason}, usage={chunk.get('usage')}")

                elif chunk['type'] == 'message_stop':
                    metrics = chunk.get('amazon-bedrock-invocationMetrics', {})
                    if not stop_reason:
                        stop_reason = metrics.get('stopReason')
                    logger.info(f"message_stop: stop_reason={stop_reason}, metrics={metrics}")
                    break

            # Fallback: parse any tool_input_buffers that were not parsed via content_block_stop
            for idx, buffer in tool_input_buffers.items():
                if idx < len(content_blocks) and content_blocks[idx].get('type') == 'tool_use':
                    if not content_blocks[idx].get('input'):
                        if buffer:
                            try:
                                tool_input = json.loads(buffer)
                                content_blocks[idx]['input'] = tool_input
                                logger.warning(f"Fallback parsed tool input for block {idx}: {list(tool_input.keys())} (buffer_len={len(buffer)})")
                            except json.JSONDecodeError as e:
                                logger.error(f"Fallback parse failed for block {idx} (buffer_len={len(buffer)}): {e}, buffer_content={repr(buffer[:200])}")
                                content_blocks[idx].setdefault('input', {})
            
            # Check if there are any tool uses
            has_tool_use = any(block.get("type") == "tool_use" for block in content_blocks)

            # Log content blocks for debugging
            logger.info(f"Content blocks: {[{'type': b.get('type'), 'name': b.get('name')} for b in content_blocks]}")

            # Handle max_tokens truncation: tool_use blocks may be incomplete
            if stop_reason == "max_tokens" and has_tool_use:
                logger.warning("Response truncated by max_tokens with incomplete tool_use blocks")
                await websocket.send_json({
                    "type": "error",
                    "message": "Model output was truncated (max_tokens). Please try a simpler request."
                })
                break

            # If no tool use, send final response
            if stop_reason != "tool_use" and not has_tool_use:
                await websocket.send_json({
                    "type": "response",
                    "content": current_text,
                    "toolCalls": all_tool_calls
                })
                break
            
            # Handle tool use
            tool_results = []
            
            for block in content_blocks:
                if block.get("type") == "tool_use":
                    tool_name = block.get("name")
                    tool_input = block.get("input", {})
                    tool_use_id = block.get("id")
                    
                    logger.info(f"Tool use block: name={tool_name}, input_keys={list(tool_input.keys())}, has_input={bool(tool_input)}")
                    
                    # Send tool call notification
                    await websocket.send_json({
                        "type": "tool_call",
                        "name": tool_name,
                        "input": tool_input
                    })
                    
                    logger.info(f"Calling tool: {tool_name}")
                    
                    # Special handling for code execution
                    if tool_name in ("execute-code", "execute-python-code"):
                        logger.info(f"Detected {tool_name}, extracting parameters...")
                        logger.info(f"Full tool_input: {tool_input}")
                        # Extract skill, code, and language from input
                        skill = tool_input.get("skill", "code-execution")
                        code = tool_input.get("code", "")
                        language = tool_input.get("language", "python")
                        logger.info(f"Skill: {skill}, Language: {language}, Code length: {len(code)}")
                        if not code:
                            logger.error(f"No code provided! tool_input keys: {list(tool_input.keys())}")
                        exec_result = await execute_code_in_sandbox(mcp_url, skill, code, language)
                        logger.info(f"Code execution result: {exec_result.get('text', '')[:200]}")
                        result = exec_result.get("text", "Code executed")
                        execution_info = exec_result.get("execution")
                        files = exec_result.get("files", [])
                    else:
                        result = await call_mcp_tool(mcp_url, tool_name, tool_input)
                        execution_info = None
                        files = []

                    # Append file download links to result so the model can reference them
                    result_for_model = result
                    if files:
                        links = "\n\nGenerated files:\n" + "\n".join(
                            f"- [{f.get('filename', 'file')}]({f.get('download_url', '')})"
                            for f in files
                        )
                        result_for_model = result + links

                    # Record tool call
                    all_tool_calls.append({
                        "name": tool_name,
                        "input": tool_input,
                        "result": result
                    })

                    # Send tool result with execution info to frontend
                    tool_result_msg = {
                        "type": "tool_result",
                        "name": tool_name,
                        "result": result
                    }
                    if execution_info:
                        tool_result_msg["execution"] = execution_info
                    if files:
                        tool_result_msg["files"] = files

                    await websocket.send_json(tool_result_msg)

                    # Send result with file links to Bedrock so model can mention them
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result_for_model,
                    })

            # Add assistant message and tool results to conversation
            # invoke_model uses Anthropic Messages API format
            messages.append({"role": "assistant", "content": content_blocks})
            messages.append({"role": "user", "content": tool_results})
            body["messages"] = messages

        # If we hit max iterations
        if iteration >= max_iterations - 1:
            await websocket.send_json({
                "type": "response",
                "content": "Maximum tool use iterations reached.",
                "toolCalls": all_tool_calls
            })
        
        await websocket.close()

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
            await websocket.close()
        except:
            pass
