"""Admin API endpoints for skill management.

Provides endpoints for the admin dashboard to manage Claude Skills.
"""

import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.deps import get_skill_loader
from app.models.skill import Skill, SkillManifest, SkillMetadata, SkillStatus
from app.services.skill_loader import SkillLoader

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


class SkillMetadataResponse(BaseModel):
    """Skill metadata response."""

    author: str | None
    version: str | None
    tags: list[str]


class SkillManifestResponse(BaseModel):
    """Skill manifest response."""

    name: str
    description: str
    license: str | None
    compatibility: str | None
    metadata: SkillMetadataResponse
    allowed_tools: list[str]
    user_invocable: bool


class SkillResponse(BaseModel):
    """Response with skill details."""

    id: str
    manifest: SkillManifestResponse
    status: SkillStatus
    source_path: str | None
    skill_md_path: str | None
    reference_files: list[str]
    script_files: list[str]
    invocation_count: int
    last_invoked_at: str | None
    load_error: str | None


class SkillListResponse(BaseModel):
    """Response with list of skills."""

    skills: list[SkillResponse]
    total: int


class ValidationResponse(BaseModel):
    """Response from skill validation."""

    valid: bool
    message: str


class SkillInstructionsResponse(BaseModel):
    """Response with skill instructions."""

    name: str
    description: str
    instructions: str


def skill_to_response(skill: Skill) -> SkillResponse:
    """Convert a Skill model to SkillResponse."""
    return SkillResponse(
        id=skill.id,
        manifest=SkillManifestResponse(
            name=skill.manifest.name,
            description=skill.manifest.description,
            license=skill.manifest.license,
            compatibility=skill.manifest.compatibility,
            metadata=SkillMetadataResponse(
                author=skill.manifest.metadata.author,
                version=skill.manifest.metadata.version,
                tags=skill.manifest.metadata.tags,
            ),
            allowed_tools=skill.manifest.allowed_tools,
            user_invocable=skill.manifest.user_invocable,
        ),
        status=skill.status,
        source_path=skill.source_path,
        skill_md_path=skill.skill_md_path,
        reference_files=skill.reference_files,
        script_files=skill.script_files,
        invocation_count=skill.invocation_count,
        last_invoked_at=skill.last_invoked_at.isoformat() if skill.last_invoked_at else None,
        load_error=skill.load_error,
    )


@router.get("/skills", response_model=SkillListResponse)
async def list_skills(
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
) -> SkillListResponse:
    """List all Claude Skills."""
    skills = skill_loader.skills
    return SkillListResponse(
        skills=[skill_to_response(s) for s in skills.values()],
        total=len(skills),
    )


@router.get("/skills/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: str,
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
) -> SkillResponse:
    """Get a skill by ID."""
    skill = skill_loader.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    return skill_to_response(skill)


@router.get("/skills/{skill_id}/instructions", response_model=SkillInstructionsResponse)
async def get_skill_instructions(
    skill_id: str,
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
) -> SkillInstructionsResponse:
    """Get the full instructions for a skill."""
    skill = skill_loader.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    return SkillInstructionsResponse(
        name=skill.manifest.name,
        description=skill.manifest.description,
        instructions=skill.manifest.instructions,
    )


@router.post("/skills/{skill_id}/reload", response_model=SkillResponse)
async def reload_skill(
    skill_id: str,
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
) -> SkillResponse:
    """Reload a skill (hot reload)."""
    skill = await skill_loader.reload_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    return skill_to_response(skill)


@router.delete("/skills/{skill_id}")
async def delete_skill(
    skill_id: str,
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
) -> dict[str, str]:
    """Unload a skill."""
    success = await skill_loader.unload_skill(skill_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    return {"message": f"Skill {skill_id} unloaded"}


@router.post("/skills/reload-all")
async def reload_all_skills(
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
) -> dict[str, Any]:
    """Reload all skills from the skills directory."""
    count = await skill_loader.load_from_directory()
    return {
        "message": f"Reloaded {count} skills",
        "count": count,
    }


@router.post("/skills/validate", response_model=ValidationResponse)
async def validate_skill_package(
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
    file: UploadFile = File(...),
) -> ValidationResponse:
    """Validate an uploaded skill package.

    Accepts a zip file containing a Claude Skill with SKILL.md.
    """
    import tempfile
    import zipfile

    if not file.filename or not file.filename.endswith(".zip"):
        return ValidationResponse(valid=False, message="Must upload a .zip file")

    # Save to temp directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        zip_path = temp_path / "skill.zip"

        # Write uploaded file
        content = await file.read()
        zip_path.write_bytes(content)

        # Extract
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(temp_path / "extracted")
        except zipfile.BadZipFile:
            return ValidationResponse(valid=False, message="Invalid zip file")

        # Find skill directory (could be root or single subdirectory)
        extracted = temp_path / "extracted"
        skill_dirs = [d for d in extracted.iterdir() if d.is_dir()]

        if len(skill_dirs) == 1:
            skill_path = skill_dirs[0]
        else:
            skill_path = extracted

        # Validate
        valid, message = await skill_loader.validate_skill_package(skill_path)
        return ValidationResponse(valid=valid, message=message)


@router.post("/skills/upload")
async def upload_skill_package(
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
    file: UploadFile = File(...),
) -> SkillResponse:
    """Upload and install a Claude Skill package.

    Accepts a zip file containing a skill with SKILL.md.
    """
    import shutil
    import tempfile
    import zipfile

    from app.core.config import get_settings

    settings = get_settings()

    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Must upload a .zip file")

    # Save to temp directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        zip_path = temp_path / "skill.zip"

        # Write uploaded file
        content = await file.read()
        zip_path.write_bytes(content)

        # Extract
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(temp_path / "extracted")
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Invalid zip file")

        # Find skill directory
        extracted = temp_path / "extracted"
        skill_dirs = [d for d in extracted.iterdir() if d.is_dir()]

        if len(skill_dirs) == 1:
            skill_path = skill_dirs[0]
        else:
            skill_path = extracted

        # Validate first
        valid, message = await skill_loader.validate_skill_package(skill_path)
        if not valid:
            raise HTTPException(status_code=400, detail=message)

        # Get skill name from directory (should match the name in SKILL.md)
        skill_name = skill_path.name

        # Copy to skills directory
        dest_path = settings.skills_path / skill_name
        if dest_path.exists():
            shutil.rmtree(dest_path)

        shutil.copytree(skill_path, dest_path)

        # Load the skill
        skill = await skill_loader.load_skill(dest_path)
        if not skill:
            raise HTTPException(status_code=500, detail="Failed to load skill")

        return skill_to_response(skill)
