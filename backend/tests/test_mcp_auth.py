"""Tests for MCP API Key authentication."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import create_app


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.mcp_auth_enabled = False
    settings.mcp_api_keys = []
    return settings


class TestMCPAuth:
    """Test MCP endpoint authentication."""

    def test_no_auth_when_disabled(self, client, mock_settings):
        """Should allow requests when auth is disabled."""
        mock_settings.mcp_auth_enabled = False
        
        with patch("app.api.deps.get_settings", return_value=mock_settings):
            response = client.get("/mcp")
            assert response.status_code != 401

    def test_reject_without_key_when_enabled(self, client, mock_settings):
        """Should reject requests without API key when auth is enabled."""
        mock_settings.mcp_auth_enabled = True
        mock_settings.mcp_api_keys = ["sk-valid-key"]
        
        with patch("app.api.deps.get_settings", return_value=mock_settings):
            response = client.get("/mcp")
            assert response.status_code == 401
            assert "Invalid or missing API key" in response.json()["detail"]

    def test_reject_invalid_key(self, client, mock_settings):
        """Should reject requests with invalid API key."""
        mock_settings.mcp_auth_enabled = True
        mock_settings.mcp_api_keys = ["sk-valid-key"]
        
        with patch("app.api.deps.get_settings", return_value=mock_settings):
            response = client.get(
                "/mcp",
                headers={"X-API-Key": "sk-wrong-key"}
            )
            assert response.status_code == 401

    def test_accept_valid_key(self, client, mock_settings):
        """Should accept requests with valid API key."""
        mock_settings.mcp_auth_enabled = True
        mock_settings.mcp_api_keys = ["sk-valid-key"]
        
        with patch("app.api.deps.get_settings", return_value=mock_settings):
            response = client.get(
                "/mcp",
                headers={"X-API-Key": "sk-valid-key"}
            )
            # Should not be 401 (might be other status depending on server state)
            assert response.status_code != 401

    def test_accept_any_of_multiple_keys(self, client, mock_settings):
        """Should accept any valid key when multiple are configured."""
        mock_settings.mcp_auth_enabled = True
        mock_settings.mcp_api_keys = ["sk-key-1", "sk-key-2", "sk-key-3"]
        
        with patch("app.api.deps.get_settings", return_value=mock_settings):
            # Test second key
            response = client.get(
                "/mcp",
                headers={"X-API-Key": "sk-key-2"}
            )
            assert response.status_code != 401

    def test_allow_when_no_keys_configured(self, client, mock_settings):
        """Should allow requests when auth enabled but no keys configured (dev mode)."""
        mock_settings.mcp_auth_enabled = True
        mock_settings.mcp_api_keys = []
        
        with patch("app.api.deps.get_settings", return_value=mock_settings):
            response = client.get("/mcp")
            assert response.status_code != 401

    def test_post_endpoint_requires_auth(self, client, mock_settings):
        """Should require auth for POST requests too."""
        mock_settings.mcp_auth_enabled = True
        mock_settings.mcp_api_keys = ["sk-valid-key"]
        
        with patch("app.api.deps.get_settings", return_value=mock_settings):
            response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1}
            )
            assert response.status_code == 401

    def test_sse_endpoint_requires_auth(self, client, mock_settings):
        """Should require auth for SSE endpoint."""
        mock_settings.mcp_auth_enabled = True
        mock_settings.mcp_api_keys = ["sk-valid-key"]
        
        with patch("app.api.deps.get_settings", return_value=mock_settings):
            response = client.get("/mcp/sse")
            assert response.status_code == 401

    def test_delete_endpoint_requires_auth(self, client, mock_settings):
        """Should require auth for DELETE (close session) endpoint."""
        mock_settings.mcp_auth_enabled = True
        mock_settings.mcp_api_keys = ["sk-valid-key"]
        
        with patch("app.api.deps.get_settings", return_value=mock_settings):
            response = client.delete("/mcp")
            assert response.status_code == 401
