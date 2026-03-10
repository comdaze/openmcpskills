"""FastAPI dependencies for dependency injection."""

import logging
import secrets
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

# Internal bypass token for server-to-server calls (e.g. playground → MCP).
# NOTE: With multiple uvicorn workers each process generates its own token,
# so token-based bypass is unreliable.  We also check for localhost origin
# in verify_mcp_auth as a reliable cross-worker bypass.
INTERNAL_BYPASS_TOKEN = secrets.token_hex(32)

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


async def _verify_auth_internal(
    bearer_token: HTTPAuthorizationCredentials | None,
    api_key_from_header: str | None,
    api_key_from_query: str | None,
    required_scopes: list[str] | None = None,
    allow_id_token: bool = False,
) -> dict | str | None:
    """Shared auth verification logic used by both MCP and Admin auth deps."""
    settings = get_settings()

    # Check if Cognito auth is enabled (takes priority)
    if settings.cognito_enabled:
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

                payload = await cognito_service.verify_token(
                    bearer_token.credentials,
                    required_scopes=required_scopes,
                    allow_id_token=allow_id_token,
                )
                logger.debug(f"Cognito auth successful for client: {payload.get('client_id')}")
                return payload

            except ValueError as e:
                logger.warning(f"Cognito token verification failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid token: {e}",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        # No bearer token when Cognito is enabled — fall through to API key only if also enabled
        if not settings.mcp_auth_enabled:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization token required",
                headers={"WWW-Authenticate": "Bearer"},
            )
    elif bearer_token:
        # Cognito disabled but Bearer token present (e.g. local OAuth from
        # MCP Streamable HTTP clients like Kiro).  Accept it as passthrough
        # when API key auth is also disabled; otherwise try it as an API key.
        if not settings.mcp_auth_enabled:
            logger.debug("Accepting Bearer token (local OAuth passthrough)")
            return {"sub": "local-oauth", "token": bearer_token.credentials}
        # When API key auth is enabled, treat Bearer credentials as a potential API key
        api_key_from_header = api_key_from_header or bearer_token.credentials

    # Fall back to API key authentication
    if settings.mcp_auth_enabled:
        api_key = api_key_from_header or api_key_from_query

        # Check env-var keys first (backward compat)
        if settings.mcp_api_keys_list:
            if api_key and api_key in settings.mcp_api_keys_list:
                return api_key

        # Check DynamoDB keys
        if api_key:
            from app.services.api_key_store import get_api_key_store

            store = get_api_key_store()
            if store:
                key_id = await store.verify_key(api_key)
                if key_id:
                    return api_key

        # No valid keys configured at all — dev mode passthrough
        if not settings.mcp_api_keys_list:
            from app.services.api_key_store import get_api_key_store

            store = get_api_key_store()
            if not store or store.active_count == 0:
                return None

        # Use Bearer challenge when Cognito is the primary auth method
        # so OAuth clients (e.g. QuickSuite) can discover auth properly
        if settings.cognito_enabled:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # No auth enabled — allow all requests
    return None


async def verify_mcp_auth(
    request: Request,
    api_key_from_header: str | None = Security(api_key_header),
    api_key_from_query: str | None = Security(api_key_query),
    bearer_token: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict | str | None:
    """Verify MCP authentication — requires openmcpskills-api/mcp scope for JWT."""
    # Allow internal server-to-server calls (e.g. playground → MCP on localhost).
    # Check both token match AND localhost origin.  With multiple uvicorn workers
    # each process has a different token, so localhost check is the reliable path.
    internal_token = request.headers.get("x-internal-token")
    client_host = request.client.host if request.client else None
    if internal_token and client_host in ("127.0.0.1", "::1"):
        return {"sub": "internal-playground"}

    return await _verify_auth_internal(
        bearer_token, api_key_from_header, api_key_from_query,
        required_scopes=["openmcpskills-api/mcp"],
    )


async def verify_admin_auth(
    request: Request,
    api_key_from_header: str | None = Security(api_key_header),
    api_key_from_query: str | None = Security(api_key_query),
    bearer_token: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict | str | None:
    """Verify admin authentication — requires openmcpskills-api/admin scope for JWT.

    When all auth is disabled (cognito_enabled=False AND mcp_auth_enabled=False),
    returns None (passthrough) to avoid chicken-and-egg issues during setup.

    Same-origin requests from the frontend dashboard are allowed without credentials,
    since the frontend itself is served behind its own auth layer.
    """
    settings = get_settings()
    if not settings.cognito_enabled and not settings.mcp_auth_enabled:
        return None

    # Allow same-origin requests from the frontend dashboard (Referer/Origin check)
    origin = request.headers.get("origin", "")
    referer = request.headers.get("referer", "")
    base_url = settings.mcp_server_url.removesuffix("/mcp") if settings.mcp_server_url else ""
    if base_url and (origin == base_url or referer.startswith(base_url)):
        return {"sub": "frontend-admin", "origin": origin or referer}

    return await _verify_auth_internal(
        bearer_token, api_key_from_header, api_key_from_query,
        required_scopes=["openmcpskills-api/admin"],
        allow_id_token=True,  # Accept frontend user ID tokens
    )


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
AdminAuthDep = Annotated[dict | str | None, Depends(verify_admin_auth)]
