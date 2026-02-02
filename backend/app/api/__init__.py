"""API module for MCP Skills server."""

from app.api.mcp import router as mcp_router
from app.api.admin import router as admin_router
from app.api.health import router as health_router

__all__ = ["mcp_router", "admin_router", "health_router"]
