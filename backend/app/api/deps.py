"""FastAPI dependencies for dependency injection."""

from typing import Annotated

from fastapi import Depends

from app.services.mcp_engine import MCPEngine
from app.services.session_manager import SessionManager
from app.services.skill_loader import SkillLoader

# Global instances (initialized in main.py)
_skill_loader: SkillLoader | None = None
_session_manager: SessionManager | None = None
_mcp_engine: MCPEngine | None = None


def set_skill_loader(loader: SkillLoader) -> None:
    """Set the global skill loader instance."""
    global _skill_loader
    _skill_loader = loader


def set_session_manager(manager: SessionManager) -> None:
    """Set the global session manager instance."""
    global _session_manager
    _session_manager = manager


def set_mcp_engine(engine: MCPEngine) -> None:
    """Set the global MCP engine instance."""
    global _mcp_engine
    _mcp_engine = engine


def get_skill_loader() -> SkillLoader:
    """Get the skill loader instance."""
    if _skill_loader is None:
        raise RuntimeError("Skill loader not initialized")
    return _skill_loader


def get_session_manager() -> SessionManager:
    """Get the session manager instance."""
    if _session_manager is None:
        raise RuntimeError("Session manager not initialized")
    return _session_manager


def get_mcp_engine() -> MCPEngine:
    """Get the MCP engine instance."""
    if _mcp_engine is None:
        raise RuntimeError("MCP engine not initialized")
    return _mcp_engine


# Type aliases for FastAPI dependency injection
SkillLoaderDep = Annotated[SkillLoader, Depends(get_skill_loader)]
SessionManagerDep = Annotated[SessionManager, Depends(get_session_manager)]
MCPEngineDep = Annotated[MCPEngine, Depends(get_mcp_engine)]
