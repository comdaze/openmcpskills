"""FastAPI dependencies for dependency injection."""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Header, Request, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery, HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import get_settings
from app.services.mcp_engine import MCPEngine
from app.services.session_manager import SessionManager
from app.services.skill_loader import SkillLoader
from app.services.metadata_store import MetadataStore
from app.services.invocation_logger import InvocationLogger
from app.services.s3_store import S3SkillStore

logger = logging.getLogger(__name__)

# Global instances (initialized in main.py)
_skill_loader: SkillLoader | None = None
_session_manager: SessionManager | None = None
_mcp_engine: MCPEngine | None = None
_metadata_store: MetadataStore | None = None
_invocation_logger: InvocationLogger | None = None
_s3_store: S3SkillStore | None = None

# API Key schemes (header and query string)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)

# Bearer token scheme for Cognito JWT
bearer_scheme = HTTPBearer(auto_error=False)


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


def set_metadata_store(store: MetadataStore) -> None:
    global _metadata_store
    _metadata_store = store


def set_invocation_logger(logger: InvocationLogger) -> None:
    global _invocation_logger
    _invocation_logger = logger


def set_s3_store(store: S3SkillStore) -> None:
    global _s3_store
    _s3_store = store


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


def get_metadata_store() -> MetadataStore:
    if _metadata_store is None:
        raise RuntimeError("Metadata store not initialized")
    return _metadata_store


def get_invocation_logger() -> InvocationLogger:
    if _invocation_logger is None:
        raise RuntimeError("Invocation logger not initialized")
    return _invocation_logger


def get_s3_store() -> S3SkillStore:
    if _s3_store is None:
        raise RuntimeError("S3 store not initialized")
    return _s3_store


def get_s3_store_optional() -> S3SkillStore | None:
    return _s3_store


async def verify_mcp_auth(
    request: Request,
    api_key_from_header: str | None = Security(api_key_header),
    api_key_from_query: str | None = Security(api_key_query),
    bearer_token: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict | str | None:
    """Verify MCP authentication using multiple methods.

    Supports:
    1. Cognito JWT Bearer token (preferred for Quick Suite / AgentCore Gateway)
    2. X-API-Key header (legacy)
    3. api_key query string (legacy)

    Auth priority: Bearer token > API Key header > API Key query

    Returns:
        - dict: Decoded JWT payload if Cognito auth is used
        - str: API key if API key auth is used
        - None: If auth is disabled
        
    Raises:
        HTTPException 401 if auth is enabled and credentials are invalid.
    """
    settings = get_settings()

    # Check if Cognito auth is enabled (takes priority)
    if settings.cognito_enabled:
        # Try Bearer token first
        if bearer_token:
            try:
                from app.services.cognito_auth import get_cognito_service
                
                cognito_service = get_cognito_service()
                if cognito_service is None:
                    logger.error("Cognito service not initialized but cognito_enabled=True")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Authentication service not available",
                    )
                
                # Verify the JWT token
                payload = await cognito_service.verify_token(bearer_token.credentials)
                logger.debug(f"Cognito auth successful for client: {payload.get('client_id')}")
                return payload
                
            except ValueError as e:
                logger.warning(f"Cognito token verification failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid token: {e}",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        
        # No bearer token provided when Cognito is enabled
        # Check if we should also allow API key fallback
        if not settings.mcp_auth_enabled:
            # Cognito is enabled but no token - reject
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization token required",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Fall back to API key authentication
    if settings.mcp_auth_enabled:
        # No API keys configured - allow all (dev mode warning logged elsewhere)
        if not settings.mcp_api_keys_list:
            return None

        # Try header first, then query string
        api_key = api_key_from_header or api_key_from_query

        # Validate the provided key
        if not api_key or api_key not in settings.mcp_api_keys_list:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        return api_key

    # No auth enabled - allow all requests
    return None


# Legacy function - kept for backward compatibility
async def verify_mcp_api_key(
    api_key_from_header: str | None = Security(api_key_header),
    api_key_from_query: str | None = Security(api_key_query),
) -> str | None:
    """Verify MCP API Key for authentication (legacy).

    Use verify_mcp_auth for new code - it supports both Cognito JWT and API Key.
    """
    settings = get_settings()

    # Auth not enabled - allow all requests
    if not settings.mcp_auth_enabled:
        return None

    # No API keys configured - allow all (dev mode warning logged elsewhere)
    if not settings.mcp_api_keys_list:
        return None

    # Try header first, then query string
    api_key = api_key_from_header or api_key_from_query

    # Validate the provided key
    if not api_key or api_key not in settings.mcp_api_keys_list:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return api_key


# Type aliases for FastAPI dependency injection
SkillLoaderDep = Annotated[SkillLoader, Depends(get_skill_loader)]
SessionManagerDep = Annotated[SessionManager, Depends(get_session_manager)]
MCPEngineDep = Annotated[MCPEngine, Depends(get_mcp_engine)]
MCPApiKeyDep = Annotated[str | None, Depends(verify_mcp_api_key)]
MCPAuthDep = Annotated[dict | str | None, Depends(verify_mcp_auth)]
