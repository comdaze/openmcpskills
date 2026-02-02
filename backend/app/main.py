"""Main FastAPI application for Open MCP Skills server."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin_router, health_router, mcp_router
from app.api.deps import (
    set_mcp_engine,
    set_session_manager,
    set_skill_loader,
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
    mcp_engine = MCPEngine(skill_loader, session_manager)

    # Set global instances for dependency injection
    set_skill_loader(skill_loader)
    set_session_manager(session_manager)
    set_mcp_engine(mcp_engine)

    # Start session manager (for cleanup task)
    await session_manager.start()

    # Load skills from directory
    skills_path = settings.skills_path
    logger.info(f"Loading Claude Skills from: {skills_path}")
    count = await skill_loader.load_from_directory(skills_path)
    logger.info(f"Loaded {count} Claude Skills")

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
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id"],
    )

    # Include routers
    app.include_router(health_router)
    app.include_router(mcp_router)
    app.include_router(admin_router)

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
