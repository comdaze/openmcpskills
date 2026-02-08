"""Health check endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import get_session_manager, get_skill_loader
from app.core.config import get_settings
from app.services.session_manager import SessionManager
from app.services.skill_loader import SkillLoader

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check(
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
) -> dict[str, Any]:
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "skills_loaded": len(skill_loader.active_skills),
    }


@router.get("/ready")
async def readiness_check(
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> dict[str, Any]:
    """Readiness check with component status."""
    settings = get_settings()

    return {
        "status": "ready",
        "components": {
            "skills": {
                "loaded": len(skill_loader.skills),
                "active": len(skill_loader.active_skills),
            },
            "sessions": {
                "active": session_manager.get_active_session_count(),
            },
        },
        "version": settings.app_version,
        "environment": settings.environment,
    }


@router.get("/info")
async def server_info(
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
) -> dict[str, Any]:
    """Get server information for clients."""
    settings = get_settings()

    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "storage_backend": "S3 + DynamoDB",
    }
