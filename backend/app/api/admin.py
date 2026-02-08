"""Admin API endpoints for skill management.

Provides endpoints for the admin dashboard to manage Claude Skills.
"""

import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.deps import get_skill_loader
from app.core.config import get_settings
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

        # If S3 mode, persist to S3 + DynamoDB
        if settings.storage_backend == "s3":
            import json as _json
            from app.api.deps import get_s3_store, get_metadata_store
            s3_store = get_s3_store()
            metadata_store = get_metadata_store()

            # Determine next version
            versions = await s3_store.list_versions(skill_name)
            next_v = f"v{len(versions) + 1}"

            s3_key = await s3_store.upload_skill(skill_name, next_v, dest_path)
            await metadata_store.put_skill(
                skill_name,
                name=skill.manifest.name,
                description=skill.manifest.description,
                version=next_v,
                status="active",
                s3_key=s3_key,
                manifest_json=_json.dumps(skill.manifest.model_dump(exclude={"instructions"})),
                author=skill.manifest.metadata.author,
                tags=skill.manifest.metadata.tags,
            )

        return skill_to_response(skill)


# ---- Phase 3: Storage endpoints ----

@router.get("/skills/{skill_id}/versions")
async def list_skill_versions(skill_id: str) -> dict[str, Any]:
    """List all versions of a skill (S3 mode only)."""
    settings = get_settings()
    if settings.storage_backend != "s3":
        raise HTTPException(status_code=400, detail="Versioning requires storage_backend=s3")

    from app.api.deps import get_s3_store
    s3_store = get_s3_store()
    versions = await s3_store.list_versions(skill_id)
    return {"skill_id": skill_id, "versions": versions}


@router.post("/skills/{skill_id}/rollback")
async def rollback_skill(
    skill_id: str,
    version: str,
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
) -> dict[str, str]:
    """Rollback a skill to a specific version (S3 mode only)."""
    settings = get_settings()
    if settings.storage_backend != "s3":
        raise HTTPException(status_code=400, detail="Rollback requires storage_backend=s3")

    from app.api.deps import get_s3_store, get_metadata_store
    s3_store = get_s3_store()
    metadata_store = get_metadata_store()

    local_path = await s3_store.download_skill(skill_id, version)
    skill = await skill_loader.load_skill(local_path)
    if not skill:
        raise HTTPException(status_code=500, detail="Failed to load rolled-back skill")

    # Update metadata version
    meta = await metadata_store.get_skill(skill_id)
    if meta:
        await metadata_store.put_skill(
            skill_id, name=meta["name"], description=meta["description"],
            version=version, status="active",
            s3_key=f"skills/{skill_id}/{version}/",
            manifest_json=meta.get("manifest_json", "{}"),
        )

    return {"message": f"Rolled back {skill_id} to {version}"}


@router.get("/skills/{skill_id}/logs")
async def get_skill_logs(skill_id: str, limit: int = 50) -> dict[str, Any]:
    """Get invocation logs for a skill (S3 mode only)."""
    settings = get_settings()
    if settings.storage_backend != "s3":
        raise HTTPException(status_code=400, detail="Logs require storage_backend=s3")

    from app.api.deps import get_invocation_logger
    inv_logger = get_invocation_logger()
    logs = await inv_logger.query_logs(skill_id, limit=limit)
    return {"skill_id": skill_id, "logs": logs, "count": len(logs)}


# ---- GitHub Import ----

class GitHubImportRequest(BaseModel):
    """Request to import skills from GitHub."""
    url: str  # e.g. https://github.com/anthropics/skills/tree/main/skills


@router.post("/skills/import-github")
async def import_from_github(
    req: GitHubImportRequest,
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
) -> dict[str, Any]:
    """Import skills from a GitHub repository URL.
    
    Supports URLs like:
    - https://github.com/anthropics/skills/tree/main/skills
    - https://github.com/owner/repo/tree/branch/path/to/skills
    """
    import re
    import shutil
    import tempfile
    import subprocess

    # Parse GitHub URL
    pattern = r"https://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/?(.*)"
    match = re.match(pattern, req.url)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid GitHub URL format")

    owner, repo, branch, path = match.groups()
    path = path.rstrip("/")

    settings = get_settings()
    imported = []
    errors = []

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        repo_path = temp_path / repo

        # Clone repository
        try:
            if path:
                # Use sparse checkout for subdirectory
                subprocess.run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse",
                               f"https://github.com/{owner}/{repo}.git", str(repo_path)],
                              check=True, capture_output=True, timeout=60)
                subprocess.run(["git", "-C", str(repo_path), "sparse-checkout", "set", path],
                              check=True, capture_output=True, timeout=30)
                subprocess.run(["git", "-C", str(repo_path), "checkout", branch],
                              check=True, capture_output=True, timeout=30)
            else:
                # Full clone for root directory
                subprocess.run(["git", "clone", "--depth", "1", "--branch", branch,
                               f"https://github.com/{owner}/{repo}.git", str(repo_path)],
                              check=True, capture_output=True, timeout=60)
        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=400, detail=f"Git clone failed: {e.stderr.decode()[:200]}")
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=408, detail="Git clone timed out")

        # Find skill directories
        skills_dir = repo_path / path if path else repo_path
        if not skills_dir.exists():
            raise HTTPException(status_code=404, detail=f"Path not found: {path}")

        # Check if URL points to a single skill directory
        if (skills_dir / "SKILL.md").exists():
            raise HTTPException(
                status_code=400,
                detail=f"URL points to a single skill '{skills_dir.name}'. Please use the parent directory URL to import skills."
            )

        for item in skills_dir.iterdir():
            if not item.is_dir():
                continue
            # Check if it's a valid skill (has SKILL.md)
            if not (item / "SKILL.md").exists():
                continue

            skill_name = item.name
            dest_path = settings.skills_path / skill_name

            try:
                if dest_path.exists():
                    shutil.rmtree(dest_path)
                shutil.copytree(item, dest_path)

                skill = await skill_loader.load_skill(dest_path)
                if skill:
                    # S3 persist
                    if settings.storage_backend == "s3":
                        import json as _json
                        from app.api.deps import get_s3_store, get_metadata_store
                        s3_store = get_s3_store()
                        metadata_store = get_metadata_store()
                        versions = await s3_store.list_versions(skill_name)
                        next_v = f"v{len(versions) + 1}"
                        s3_key = await s3_store.upload_skill(skill_name, next_v, dest_path)
                        await metadata_store.put_skill(
                            skill_name, name=skill.manifest.name, description=skill.manifest.description,
                            version=next_v, status="active", s3_key=s3_key,
                            manifest_json=_json.dumps(skill.manifest.model_dump(exclude={"instructions"})),
                            author=skill.manifest.metadata.author, tags=skill.manifest.metadata.tags,
                        )
                    imported.append(skill_name)
                else:
                    errors.append({"skill": skill_name, "error": "Failed to load"})
            except Exception as e:
                errors.append({"skill": skill_name, "error": str(e)[:100]})

    return {"imported": imported, "count": len(imported), "errors": errors}
