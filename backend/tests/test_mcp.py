"""Tests for MCP endpoint and Claude Skills protocol handling."""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
async def client():
    """Create async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_ready_check(client: AsyncClient):
    """Test readiness endpoint."""
    response = await client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert "components" in data


@pytest.mark.asyncio
async def test_mcp_initialize(client: AsyncClient):
    """Test MCP initialize request."""
    response = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0",
                },
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    assert "result" in data
    assert data["result"]["protocolVersion"] == "2025-11-25"
    assert "capabilities" in data["result"]
    assert "serverInfo" in data["result"]


@pytest.mark.asyncio
async def test_mcp_tools_list(client: AsyncClient):
    """Test MCP tools/list request."""
    response = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 2
    assert "result" in data
    assert "tools" in data["result"]
    # Should have our Claude Skills
    tools = data["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "hello-world" in tool_names
    assert "calculator" in tool_names
    assert "web-search" in tool_names
    assert "code-review" in tool_names


@pytest.mark.asyncio
async def test_mcp_tools_call_returns_instructions(client: AsyncClient):
    """Test MCP tools/call returns skill instructions."""
    response = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "hello-world",
                "arguments": {},
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 3
    assert "result" in data
    assert data["result"]["isError"] is False
    content = data["result"]["content"]
    assert len(content) > 0
    # Should contain skill instructions
    text = content[0]["text"]
    assert "Skill: hello-world" in text
    assert "greeting" in text.lower()


@pytest.mark.asyncio
async def test_mcp_prompts_list(client: AsyncClient):
    """Test MCP prompts/list returns skills as prompts."""
    response = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "prompts/list",
            "params": {},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 4
    assert "result" in data
    assert "prompts" in data["result"]
    prompts = data["result"]["prompts"]
    prompt_names = [p["name"] for p in prompts]
    assert "hello-world" in prompt_names


@pytest.mark.asyncio
async def test_mcp_prompts_get(client: AsyncClient):
    """Test MCP prompts/get returns skill instructions as messages."""
    response = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "prompts/get",
            "params": {
                "name": "calculator",
                "arguments": {},
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 5
    assert "result" in data
    assert "messages" in data["result"]
    assert len(data["result"]["messages"]) > 0


@pytest.mark.asyncio
async def test_mcp_ping(client: AsyncClient):
    """Test MCP ping request."""
    response = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 6,
            "method": "ping",
            "params": {},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 6
    assert "result" in data


@pytest.mark.asyncio
async def test_mcp_session_header(client: AsyncClient):
    """Test that session ID is returned in header."""
    response = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0",
                },
            },
        },
    )
    assert response.status_code == 200
    assert "Mcp-Session-Id" in response.headers or "mcp-session-id" in response.headers


@pytest.mark.asyncio
async def test_mcp_invalid_json(client: AsyncClient):
    """Test handling of invalid JSON."""
    response = await client.post(
        "/mcp",
        content="not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_mcp_method_not_found(client: AsyncClient):
    """Test handling of unknown method."""
    response = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 99,
            "method": "unknown/method",
            "params": {},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_mcp_skill_not_found(client: AsyncClient):
    """Test handling of non-existent skill."""
    response = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 100,
            "method": "tools/call",
            "params": {
                "name": "non-existent-skill",
                "arguments": {},
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_admin_list_skills(client: AsyncClient):
    """Test admin API to list skills."""
    response = await client.get("/admin/skills")
    assert response.status_code == 200
    data = response.json()
    assert "skills" in data
    assert "total" in data
    assert data["total"] >= 4  # We have 4 sample skills


@pytest.mark.asyncio
async def test_admin_get_skill(client: AsyncClient):
    """Test admin API to get a single skill."""
    response = await client.get("/admin/skills/hello-world")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "hello-world"
    assert data["manifest"]["name"] == "hello-world"


@pytest.mark.asyncio
async def test_admin_get_skill_instructions(client: AsyncClient):
    """Test admin API to get skill instructions."""
    response = await client.get("/admin/skills/calculator/instructions")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "calculator"
    assert "instructions" in data
    assert len(data["instructions"]) > 0
