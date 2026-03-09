"""Main FastAPI application for Open MCP Skills server."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin_router, health_router, mcp_router, playground_router
from app.api.deps import (
    set_mcp_engine,
    set_session_manager,
    set_skill_loader,
    set_metadata_store,
    set_invocation_logger,
    set_s3_store,
)
from app.core.config import get_settings
from app.services.mcp_engine import MCPEngine
from app.services.session_manager import SessionManager
from app.services.skill_loader import SkillLoader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler.

    Initializes and cleans up application resources.
    """
    settings = get_settings()
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")

    # Initialize services
    skill_loader = SkillLoader()
    session_manager = SessionManager()

    metadata_store = None
    invocation_logger = None
    s3_store = None
    code_interpreter = None

    # Initialize persistent API key store (always enabled, independent of storage_backend)
    from app.services.api_key_store import ApiKeyStore, set_api_key_store

    api_key_store = ApiKeyStore()
    try:
        key_count = await api_key_store.load_all()
        set_api_key_store(api_key_store)
        logger.info(f"API key store initialized ({key_count} active keys)")
    except Exception as e:
        logger.warning(f"API key store initialization failed (non-fatal): {e}")
        set_api_key_store(api_key_store)

    if settings.storage_backend == "s3":
        from app.services.s3_store import S3SkillStore
        from app.services.metadata_store import MetadataStore
        from app.services.invocation_logger import InvocationLogger

        s3_store = S3SkillStore()
        metadata_store = MetadataStore()
        invocation_logger = InvocationLogger()
        set_metadata_store(metadata_store)
        set_invocation_logger(invocation_logger)
        set_s3_store(s3_store)
        logger.info("Storage backend: S3 + DynamoDB")
    else:
        logger.info("Storage backend: local filesystem")

    # Initialize Code Interpreter if enabled
    code_interpreter = None
    if settings.code_interpreter_enabled:
        from app.services.code_interpreter import CodeInterpreterService

        code_interpreter = CodeInterpreterService(
            region=settings.aws_region,
            code_interpreter_id=settings.code_interpreter_id,
            default_timeout=settings.code_interpreter_default_timeout,
            session_timeout=settings.code_interpreter_session_timeout,
            s3_bucket=settings.code_interpreter_s3_bucket,
            s3_prefix=settings.code_interpreter_s3_prefix,
        )
        logger.info("Code Interpreter service initialized")

    # Initialize Cognito authentication service if enabled
    if settings.cognito_enabled:
        from app.services.cognito_auth import CognitoAuthService, set_cognito_service
        
        cognito_region = settings.cognito_region or settings.aws_region
        if not settings.cognito_user_pool_id:
            logger.error("Cognito enabled but COGNITO_USER_POOL_ID not set")
        else:
            cognito_service = CognitoAuthService(
                region=cognito_region,
                user_pool_id=settings.cognito_user_pool_id,
                allowed_client_ids=settings.cognito_allowed_client_ids_list,
            )
            set_cognito_service(cognito_service)
            logger.info(f"Cognito S2S authentication enabled")
            logger.info(f"  User Pool ID: {settings.cognito_user_pool_id}")
            logger.info(f"  Region: {cognito_region}")
            if settings.cognito_allowed_client_ids_list:
                logger.info(f"  Allowed Client IDs: {settings.cognito_allowed_client_ids_list}")
            else:
                logger.info(f"  Allowed Client IDs: (any)")
    else:
        logger.info("Cognito authentication: disabled")

    mcp_engine = MCPEngine(
        skill_loader,
        session_manager,
        metadata_store,
        invocation_logger,
        code_interpreter,
    )

    # Set global instances for dependency injection
    set_skill_loader(skill_loader)
    set_session_manager(session_manager)
    set_mcp_engine(mcp_engine)

    # Start session manager (for cleanup task)
    await session_manager.start()

    # Load skills
    skills_path = settings.skills_path
    if settings.storage_backend == "s3":
        logger.info("Syncing skills from S3...")
        s3_count = await s3_store.sync_all_to_local()
        if s3_count > 0:
            skills_path = settings.skill_cache_dir
            logger.info(f"Synced {s3_count} skills from S3, loading from cache")
        else:
            logger.info("No skills in S3 yet, loading from local directory")

    logger.info(f"Loading Claude Skills from: {skills_path}")
    count = await skill_loader.load_from_directory(skills_path, lazy=True)
    logger.info(f"Registered {count} Claude Skills (lazy loading enabled)")

    # Restore invocation counts from DynamoDB via batch read.
    # Counts are stored as pending and applied lazily when skills are first accessed.
    if metadata_store:
        all_ids = skill_loader.all_skill_ids
        counts = await metadata_store.batch_get_invocation_counts(all_ids)
        skill_loader.set_pending_counts(counts)
        logger.info(f"Loaded invocation counts for {len(counts)} skills from DynamoDB")

    # Pre-warm: eagerly load all skills and build tools cache so the
    # first tools/list request doesn't pay the lazy-loading cost.
    import time as _time
    _warm_start = _time.monotonic()
    for sid in skill_loader.all_skill_ids:
        await skill_loader.get_skill(sid)
    await mcp_engine._build_tools_cache()
    logger.info(
        f"Pre-warmed {len(skill_loader.skills)} skills + tools cache "
        f"in {(_time.monotonic() - _warm_start) * 1000:.0f}ms"
    )

    # Start file watcher if enabled
    watcher_task = None
    if settings.skills_watch_enabled:
        watcher_task = asyncio.create_task(
            watch_skills_directory(skill_loader, skills_path)
        )
        logger.info("Skills file watcher started")

    yield

    # Cleanup
    logger.info("Shutting down...")

    if watcher_task:
        watcher_task.cancel()
        try:
            await watcher_task
        except asyncio.CancelledError:
            pass

    # Cleanup Code Interpreter
    if code_interpreter:
        await code_interpreter.cleanup()
        logger.info("Code Interpreter cleaned up")

    await session_manager.stop()
    logger.info("Shutdown complete")


async def watch_skills_directory(
    skill_loader: SkillLoader,
    skills_path: str,
) -> None:
    """Watch skills directory for changes and hot-reload."""
    try:
        from watchfiles import awatch

        async for changes in awatch(skills_path):
            for change_type, path in changes:
                logger.info(f"Skills directory change: {change_type} {path}")

            # Reload all skills on any change
            count = await skill_loader.load_from_directory()
            logger.info(f"Reloaded {count} skills after file change")

    except ImportError:
        logger.warning("watchfiles not installed, file watching disabled")
    except asyncio.CancelledError:
        pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Cloud-native MCP Server for Claude Skills as a Service",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id"],
    )

    # Include routers
    app.include_router(health_router)
    app.include_router(mcp_router)
    app.include_router(admin_router)
    app.include_router(playground_router)

    # MCP Streamable HTTP OAuth endpoints
    # Kiro and other MCP clients do OAuth discovery before connecting.
    # We provide minimal endpoints so clients can complete the handshake.
    # When Cognito is enabled, point to the real Cognito token endpoint.

    @app.get("/.well-known/oauth-protected-resource")
    async def oauth_protected_resource():
        """RFC 9728 Protected Resource Metadata — tells clients where to authenticate."""
        _settings = get_settings()
        resource = _settings.mcp_server_url or "http://127.0.0.1:8000/mcp"
        # Always point to our own server for authorization_servers.
        # Our /.well-known/oauth-authorization-server proxies the real
        # Cognito metadata (token_endpoint, scopes, etc.) since Cognito
        # itself doesn't serve RFC 8414 metadata.
        base = resource.removesuffix("/mcp")
        return {
            "resource": resource,
            "authorization_servers": [base],
        }

    @app.get("/.well-known/openid-configuration")
    async def openid_configuration():
        """OpenID Connect Discovery — QuickSuite checks this during setup."""
        _settings = get_settings()
        if _settings.cognito_enabled and _settings.cognito_token_endpoint:
            resource = _settings.mcp_server_url or "http://127.0.0.1:8000/mcp"
            base = resource.removesuffix("/mcp")
            cognito_issuer = f"https://cognito-idp.{_settings.cognito_region or 'us-east-1'}.amazonaws.com/{_settings.cognito_user_pool_id}"
            scopes = _settings.cognito_scopes_list or ["openmcpskills-api/mcp", "openmcpskills-api/read"]
            return {
                "issuer": cognito_issuer,
                "authorization_endpoint": f"{_settings.cognito_token_endpoint.rsplit('/oauth2/', 1)[0]}/oauth2/authorize",
                "token_endpoint": _settings.cognito_token_endpoint,
                "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
                "jwks_uri": f"{cognito_issuer}/.well-known/jwks.json",
                "response_types_supported": ["code"],
                "grant_types_supported": ["client_credentials", "authorization_code"],
                "scopes_supported": scopes,
                "subject_types_supported": ["public"],
                "id_token_signing_alg_values_supported": ["RS256"],
            }
        base_url = "http://127.0.0.1:8000"
        return {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/oauth/authorize",
            "token_endpoint": f"{base_url}/oauth/token",
            "jwks_uri": f"{base_url}/.well-known/jwks.json",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "scopes_supported": ["openid"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
        }

    @app.get("/.well-known/oauth-authorization-server")
    async def oauth_metadata():
        _settings = get_settings()
        if _settings.cognito_enabled and _settings.cognito_token_endpoint:
            # Serve Cognito token endpoint via our own OAuth metadata.
            # issuer must match the authorization_servers URL in the
            # protected resource metadata (i.e. our own base URL).
            resource = _settings.mcp_server_url or "http://127.0.0.1:8000/mcp"
            base = resource.removesuffix("/mcp")
            scopes = _settings.cognito_scopes_list or ["openmcpskills-api/mcp", "openmcpskills-api/read"]
            return {
                "issuer": base,
                "token_endpoint": _settings.cognito_token_endpoint,
                "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
                "response_types_supported": ["code"],
                "grant_types_supported": ["client_credentials"],
                "scopes_supported": scopes,
            }
        # Fallback: local dev stub
        base_url = "http://127.0.0.1:8000"
        return {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/oauth/authorize",
            "token_endpoint": f"{base_url}/oauth/token",
            "registration_endpoint": f"{base_url}/oauth/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
        }

    @app.post("/oauth/register")
    async def oauth_register(request: Request):
        """Dynamic client registration — accept any client and return an ID."""
        import secrets as _secrets
        body = await request.json()
        client_id = _secrets.token_hex(16)
        return {
            "client_id": client_id,
            "client_name": body.get("client_name", "mcp-client"),
            "redirect_uris": body.get("redirect_uris", []),
            "grant_types": body.get("grant_types", ["authorization_code"]),
            "response_types": body.get("response_types", ["code"]),
            "token_endpoint_auth_method": "none",
        }

    @app.get("/oauth/authorize")
    async def oauth_authorize(
        response_type: str = "",
        client_id: str = "",
        redirect_uri: str = "",
        state: str = "",
        code_challenge: str = "",
        code_challenge_method: str = "",
    ):
        """Authorization endpoint — immediately redirect with a code."""
        import secrets as _secrets
        from starlette.responses import RedirectResponse
        code = _secrets.token_hex(16)
        sep = "&" if "?" in redirect_uri else "?"
        return RedirectResponse(f"{redirect_uri}{sep}code={code}&state={state}")

    @app.post("/oauth/token")
    async def oauth_token(request: Request):
        """Token endpoint — return a dummy bearer token."""
        import secrets as _secrets
        return {
            "access_token": _secrets.token_hex(32),
            "token_type": "Bearer",
            "expires_in": 3600,
        }

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
