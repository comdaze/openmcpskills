"""MCP Streamable HTTP API endpoints.

Implements the MCP protocol over Streamable HTTP transport.
This is the core endpoint that MCP clients connect to.
"""

import json
import logging
import uuid
from typing import Annotated, Any, AsyncGenerator

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from app.api.deps import get_mcp_engine, get_session_manager
from app.services.mcp_engine import MCPEngine
from app.services.session_manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["MCP"])

# Content types
CONTENT_TYPE_JSON = "application/json"
CONTENT_TYPE_SSE = "text/event-stream"


def generate_session_id() -> str:
    """Generate a new session ID."""
    return str(uuid.uuid4())


@router.post("")
@router.post("/")
@router.get("")
@router.get("/")
async def mcp_endpoint(
    request: Request,
    mcp_engine: Annotated[MCPEngine, Depends(get_mcp_engine)],
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
    mcp_session_id: Annotated[str | None, Header(alias="Mcp-Session-Id")] = None,
    accept: Annotated[str | None, Header()] = None,
) -> Response:
    """MCP Streamable HTTP endpoint.

    Handles MCP JSON-RPC messages over HTTP POST and GET.
    - POST: Send messages to server
    - GET: Listen for server messages via SSE
    Supports both single responses and SSE streaming.

    Headers:
    - Mcp-Session-Id: Optional session ID for session continuity
    - Accept: application/json for single response, text/event-stream for SSE
    """
    # Handle GET request - return SSE stream for listening
    if request.method == "GET":
        # GET must request SSE
        if not accept or CONTENT_TYPE_SSE not in accept:
            raise HTTPException(status_code=405, detail="GET requires Accept: text/event-stream")
        
        # Get or create session
        session_id = mcp_session_id
        if not session_id:
            session = await session_manager.create_session()
            session_id = session.id
        
        # Return SSE stream for server-initiated messages
        return StreamingResponse(
            listen_for_server_messages(mcp_engine, session_id, request),
            media_type=CONTENT_TYPE_SSE,
            headers={
                "Mcp-Session-Id": session_id,
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    
    # Handle POST request - process client messages
    # Parse request body
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Get or create session
    session_id = mcp_session_id
    if not session_id:
        session = await session_manager.create_session()
        session_id = session.id
        logger.debug(f"Created new session: {session_id}")

    # Check if batch request
    is_batch = isinstance(body, list)
    messages = body if is_batch else [body]

    # Check if client wants SSE streaming
    wants_streaming = accept and CONTENT_TYPE_SSE in accept

    # Process all messages first to check if any have responses
    responses = []
    for message in messages:
        response = await mcp_engine.handle_message(message, session_id)
        if response is not None:
            responses.append(response)

    # If no responses (all notifications), return 202 Accepted
    # This is required by MCP spec for notifications like "initialized"
    if not responses:
        return Response(
            status_code=202,
            headers={"Mcp-Session-Id": session_id},
        )

    if wants_streaming:
        # Return SSE stream for responses
        async def generate_sse():
            for response in responses:
                data = json.dumps(response)
                yield f"event: message\ndata: {data}\n\n"

        return StreamingResponse(
            generate_sse(),
            media_type=CONTENT_TYPE_SSE,
            headers={
                "Mcp-Session-Id": session_id,
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    else:
        # Return JSON response
        if is_batch:
            result = responses
        else:
            result = responses[0]

        return Response(
            content=json.dumps(result),
            media_type=CONTENT_TYPE_JSON,
            headers={"Mcp-Session-Id": session_id},
        )


async def stream_responses(
    mcp_engine: MCPEngine,
    session_id: str,
    messages: list[dict[str, Any]],
) -> AsyncGenerator[str, None]:
    """Stream MCP responses as Server-Sent Events."""
    for message in messages:
        try:
            response = await mcp_engine.handle_message(message, session_id)

            if response is not None:
                # Send response as SSE event with proper MCP format
                data = json.dumps(response)
                yield f"event: message\ndata: {data}\n\n"

        except Exception as e:
            logger.exception("Error processing MCP message in stream")
            error_response = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {
                    "code": -32603,
                    "message": str(e),
                },
            }
            yield f"event: message\ndata: {json.dumps(error_response)}\n\n"


async def listen_for_server_messages(
    mcp_engine: MCPEngine,
    session_id: str,
    request: Request,
) -> AsyncGenerator[str, None]:
    """Listen for server-initiated messages via SSE (for GET requests)."""
    import asyncio
    
    # Send initial connection event
    yield f"event: connected\ndata: {{\"sessionId\": \"{session_id}\"}}\n\n"
    
    # Keep connection alive with periodic pings
    while True:
        try:
            # Check if client disconnected
            if await request.is_disconnected():
                break
            
            # Send ping every 30 seconds
            await asyncio.sleep(30)
            yield ": ping\n\n"
            
        except asyncio.CancelledError:
            break


@router.get("/sse")
async def mcp_sse_endpoint(
    request: Request,
    mcp_engine: Annotated[MCPEngine, Depends(get_mcp_engine)],
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
    mcp_session_id: Annotated[str | None, Header(alias="Mcp-Session-Id")] = None,
) -> StreamingResponse:
    """SSE endpoint for server-initiated events.

    Clients can connect here to receive notifications about:
    - Tools list changes
    - Resources updates
    - Other server events
    """
    session_id = mcp_session_id
    if not session_id:
        session = await session_manager.create_session()
        session_id = session.id

    async def event_stream() -> AsyncGenerator[str, None]:
        """Generate SSE events."""
        # Send initial connection event
        yield f"event: connected\ndata: {{\"sessionId\": \"{session_id}\"}}\n\n"

        # Keep connection alive with periodic pings
        import asyncio
        while True:
            try:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                # Send ping every 30 seconds
                await asyncio.sleep(30)
                yield ": ping\n\n"

            except asyncio.CancelledError:
                break

    return StreamingResponse(
        event_stream(),
        media_type=CONTENT_TYPE_SSE,
        headers={
            "Mcp-Session-Id": session_id,
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.delete("")
@router.delete("/")
async def close_session(
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
    mcp_session_id: Annotated[str | None, Header(alias="Mcp-Session-Id")] = None,
) -> Response:
    """Close an MCP session.

    Called when client wants to cleanly disconnect.
    """
    if mcp_session_id:
        await session_manager.close_session(mcp_session_id)
        logger.debug(f"Closed session: {mcp_session_id}")

    return Response(status_code=204)
