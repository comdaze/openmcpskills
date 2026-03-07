"""Admin API endpoints for skill management.

Provides endpoints for the admin dashboard to manage Claude Skills.
"""

import io
import logging
import secrets
import zipfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import get_skill_loader, get_s3_store, get_s3_store_optional
from app.core.config import get_settings
from app.models.skill import Skill, SkillManifest, SkillMetadata, SkillStatus
from app.services.skill_loader import SkillLoader
from app.services.s3_store import S3SkillStore

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
    execution: dict[str, Any] | None = None


class SkillResponse(BaseModel):
    """Response with skill details."""

    id: str
    manifest: SkillManifestResponse
    status: SkillStatus
    version: str | None = None
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
            execution=skill.manifest.execution.model_dump() if skill.manifest.execution else None,
        ),
        status=skill.status,
        version=skill.manifest.metadata.version,
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
    """List all Claude Skills (including lazy-loaded ones)."""
    # Ensure all registered skills are loaded so we can return full metadata
    all_skills = []
    for skill_id in skill_loader.all_skill_ids:
        skill = await skill_loader.get_skill(skill_id)
        if skill:
            all_skills.append(skill)
    return SkillListResponse(
        skills=[skill_to_response(s) for s in all_skills],
        total=len(all_skills),
    )


@router.get("/skills/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: str,
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
) -> SkillResponse:
    """Get a skill by ID."""
    skill = await skill_loader.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    return skill_to_response(skill)


@router.get("/skills/{skill_id}/instructions", response_model=SkillInstructionsResponse)
async def get_skill_instructions(
    skill_id: str,
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
) -> SkillInstructionsResponse:
    """Get the full instructions for a skill."""
    skill = await skill_loader.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    return SkillInstructionsResponse(
        name=skill.manifest.name,
        description=skill.manifest.description,
        instructions=skill.manifest.instructions,
    )


DOWNLOAD_EXCLUDE = {".current_version", "__pycache__", ".pyc", ".DS_Store"}


@router.get("/skills/{skill_id}/download")
async def download_skill(
    skill_id: str,
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
    s3_store: Annotated[S3SkillStore | None, Depends(get_s3_store_optional)],
):
    """Download a skill as a zip file."""
    skill = await skill_loader.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    skill_dir = Path(skill.source_path) if skill.source_path else None

    # If S3 mode and local directory doesn't exist, download from S3
    if (skill_dir is None or not skill_dir.exists()) and s3_store is not None:
        skill_dir = await s3_store.download_skill(skill_id)

    if skill_dir is None or not skill_dir.exists():
        raise HTTPException(status_code=404, detail="Skill files not found on disk")

    # Build zip in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(skill_dir.rglob("*")):
            if not file_path.is_file():
                continue
            # Skip excluded files/directories
            parts = file_path.relative_to(skill_dir).parts
            if any(part in DOWNLOAD_EXCLUDE or part.endswith(".pyc") for part in parts):
                continue
            arcname = str(Path(skill_id) / file_path.relative_to(skill_dir))
            zf.write(file_path, arcname)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{skill_id}.zip"',
        },
    )


@router.post("/skills/{skill_id}/reload", response_model=SkillResponse)
async def reload_skill(
    skill_id: str,
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
    s3_store: Annotated[S3SkillStore, Depends(get_s3_store)],
) -> SkillResponse:
    """Reload a skill (hot reload).
    
    If using S3 storage, downloads the latest version from S3 before reloading.
    """
    skill = await skill_loader.reload_skill(skill_id, s3_store=s3_store)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    return skill_to_response(skill)


@router.delete("/skills/{skill_id}")
async def delete_skill(
    skill_id: str,
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
) -> dict[str, str]:
    """Unload a skill and remove its files from disk."""
    import shutil

    success = await skill_loader.unload_skill(skill_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    # Also remove from disk so the file watcher doesn't reload it
    settings = get_settings()
    skill_path = settings.skills_path / skill_id
    if skill_path.exists():
        shutil.rmtree(skill_path)
        logger.info("Removed skill directory: %s", skill_path)

    return {"message": f"Skill {skill_id} deleted"}


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
    versions = await s3_store.list_versions_with_dates(skill_id)
    return {"skill_id": skill_id, "versions": versions}


class RollbackRequest(BaseModel):
    """Rollback request body."""
    version: str


@router.post("/skills/{skill_id}/rollback")
async def rollback_skill(
    skill_id: str,
    body: RollbackRequest,
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
) -> dict[str, str]:
    """Rollback a skill to a specific version (S3 mode only)."""
    settings = get_settings()
    if settings.storage_backend != "s3":
        raise HTTPException(status_code=400, detail="Rollback requires storage_backend=s3")

    from app.api.deps import get_s3_store, get_metadata_store
    s3_store = get_s3_store()
    metadata_store = get_metadata_store()

    version = body.version

    local_path = await s3_store.download_skill(skill_id, version)
    skill = await skill_loader.load_skill(local_path)
    if not skill:
        raise HTTPException(status_code=500, detail="Failed to load rolled-back skill")

    # Update DynamoDB metadata version
    meta = await metadata_store.get_skill(skill_id)
    if meta:
        await metadata_store.put_skill(
            skill_id, name=meta["name"], description=meta["description"],
            version=version, status="active",
            s3_key=f"skills/{skill_id}/{version}/",
            manifest_json=meta.get("manifest_json", "{}"),
        )

    # Update S3 latest.json so restarts load the correct version
    import json as _json
    async with s3_store._session.client("s3", **s3_store._client_kwargs()) as s3:
        await s3.put_object(
            Bucket=s3_store._bucket,
            Key=s3_store._latest_key(skill_id),
            Body=_json.dumps({"version": version}).encode(),
        )

    return {"message": f"Rolled back {skill_id} to {version}", "version": version}


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


# ---- Skill Generation (skill-seekers) ----

class GenerateSkillRequest(BaseModel):
    """Request to generate a skill from an external source."""

    source_url: str
    source_type: str = "docs"  # "docs" | "github" | "pdf"
    skill_name: str
    description: str = ""
    custom_prompt: str = ""  # Optional user instructions for LLM enhancement


@router.post("/skills/generate", response_model=SkillResponse)
async def generate_skill(
    req: GenerateSkillRequest,
    skill_loader: Annotated[SkillLoader, Depends(get_skill_loader)],
) -> SkillResponse:
    """Generate a skill from a documentation site, GitHub repo, or PDF.

    Requires the optional ``skill-seekers`` package to be installed.
    """
    import re
    import shutil

    from app.services import seekers_bridge

    # 1. Check skill-seekers availability
    if not seekers_bridge.check_available():
        raise HTTPException(
            status_code=501,
            detail="skill-seekers is not installed. Install with: pip install 'open-mcp-skills[seekers]'",
        )

    # 2. Validate skill name (kebab-case)
    if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", req.skill_name):
        raise HTTPException(
            status_code=400,
            detail="skill_name must be kebab-case (lowercase letters, numbers, hyphens)",
        )

    if req.source_type not in ("docs", "github", "pdf"):
        raise HTTPException(status_code=400, detail="source_type must be 'docs', 'github', or 'pdf'")

    # Auto-detect: GitHub URL overrides source_type to "github"
    source_type = req.source_type
    if "github.com" in req.source_url and source_type != "github":
        logger.info("Auto-detected GitHub URL, switching source_type to 'github'")
        source_type = "github"

    # Similarly, .pdf URL overrides to "pdf"
    if req.source_url.lower().endswith(".pdf") and source_type != "pdf":
        logger.info("Auto-detected PDF URL, switching source_type to 'pdf'")
        source_type = "pdf"

    # 3. Generate via seekers_bridge
    try:
        if source_type == "github":
            skill_path = await seekers_bridge.generate_skill_from_github(
                req.source_url, req.skill_name, req.description, req.custom_prompt
            )
        elif source_type == "pdf":
            skill_path = await seekers_bridge.generate_skill_from_pdf(
                req.source_url, req.skill_name, req.description, req.custom_prompt
            )
        else:
            skill_path = await seekers_bridge.generate_skill_from_docs(
                req.source_url, req.skill_name, req.description, req.custom_prompt
            )
    except Exception as e:
        logger.error("Skill generation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")

    # 4. Install into skills directory (reuse upload flow)
    settings = get_settings()

    dest_path = settings.skills_path / req.skill_name
    if dest_path.exists():
        shutil.rmtree(dest_path)

    shutil.copytree(skill_path, dest_path)

    # Remove backup files left by enhancement step
    for bak in dest_path.glob("*.original"):
        bak.unlink(missing_ok=True)

    # Clean up temp directory
    try:
        shutil.rmtree(skill_path.parent)
    except OSError:
        pass

    # Validate
    valid, message = await skill_loader.validate_skill_package(dest_path)
    if not valid:
        shutil.rmtree(dest_path, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Generated skill invalid: {message}")

    # Load
    skill = await skill_loader.load_skill(dest_path)
    if not skill:
        raise HTTPException(status_code=500, detail="Failed to load generated skill")

    # 5. S3 persist (same pattern as upload)
    if settings.storage_backend == "s3":
        import json as _json

        from app.api.deps import get_s3_store, get_metadata_store

        s3_store = get_s3_store()
        metadata_store = get_metadata_store()
        versions = await s3_store.list_versions(req.skill_name)
        next_v = f"v{len(versions) + 1}"
        s3_key = await s3_store.upload_skill(req.skill_name, next_v, dest_path)
        await metadata_store.put_skill(
            req.skill_name,
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


@router.get("/files/download")
async def download_file(s3_key: str):
    """Generate a presigned URL for downloading a file from S3.

    Args:
        s3_key: S3 object key (e.g. output_artifacts/pptx-generator/1739621438_file.pptx)

    Returns:
        Presigned URL valid for 1 hour
    """
    settings = get_settings()
    bucket = settings.code_interpreter_s3_bucket
    if not bucket:
        raise HTTPException(status_code=500, detail="S3 bucket not configured")

    # Validate key is under output_artifacts prefix
    if not s3_key.startswith(settings.code_interpreter_s3_prefix):
        raise HTTPException(status_code=403, detail="Access denied: invalid path")

    import boto3
    from botocore.config import Config as BotoConfig
    s3_kwargs: dict = {
        "region_name": settings.aws_region,
        "config": BotoConfig(signature_version="s3v4"),
    }
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        s3_kwargs["aws_access_key_id"] = settings.aws_access_key_id
        s3_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    s3 = boto3.client("s3", **s3_kwargs)
    try:
        # Check file exists
        s3.head_object(Bucket=bucket, Key=s3_key)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")

    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": s3_key},
        ExpiresIn=3600,
    )
    filename = s3_key.rsplit("/", 1)[-1]
    # Strip timestamp prefix (e.g. "1739621438_file.pptx" -> "file.pptx")
    if "_" in filename and filename.split("_", 1)[0].isdigit():
        filename = filename.split("_", 1)[1]

    return {"download_url": url, "filename": filename, "expires_in": 3600}


@router.get("/files/stream")
async def stream_file(s3_key: str):
    """Stream a file from S3 directly through the backend.

    This avoids presigned URL issues with temporary STS credentials
    by proxying the download through the backend.

    Args:
        s3_key: S3 object key (e.g. output_artifacts/pptx-generator/1739621438_file.pptx)
    """
    settings = get_settings()
    bucket = settings.code_interpreter_s3_bucket
    if not bucket:
        raise HTTPException(status_code=500, detail="S3 bucket not configured")

    # Validate key is under output_artifacts prefix
    if not s3_key.startswith(settings.code_interpreter_s3_prefix):
        raise HTTPException(status_code=403, detail="Access denied: invalid path")

    import boto3
    from botocore.config import Config as BotoConfig
    s3_kwargs: dict = {
        "region_name": settings.aws_region,
        "config": BotoConfig(signature_version="s3v4"),
    }
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        s3_kwargs["aws_access_key_id"] = settings.aws_access_key_id
        s3_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    s3 = boto3.client("s3", **s3_kwargs)

    from botocore.exceptions import ClientError
    try:
        response = s3.get_object(Bucket=bucket, Key=s3_key)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail="File not found")
        logger.error(f"S3 get_object failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve file")
    except Exception as e:
        logger.error(f"S3 get_object failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve file")

    # Determine filename for Content-Disposition
    filename = s3_key.rsplit("/", 1)[-1]
    if "_" in filename and filename.split("_", 1)[0].isdigit():
        filename = filename.split("_", 1)[1]

    content_type = response.get("ContentType", "application/octet-stream")
    content_length = response.get("ContentLength")

    # RFC 5987: use filename* with UTF-8 encoding for non-ASCII filenames
    from urllib.parse import quote
    ascii_filename = filename.encode("ascii", "replace").decode("ascii")
    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"{ascii_filename}\"; "
            f"filename*=UTF-8''{quote(filename)}"
        ),
    }
    if content_length:
        headers["Content-Length"] = str(content_length)

    def stream_body():
        body = response["Body"]
        while chunk := body.read(64 * 1024):
            yield chunk

    return StreamingResponse(
        stream_body(),
        media_type=content_type,
        headers=headers,
    )


@router.get("/f/{short_id}")
async def short_link_redirect(short_id: str):
    """Redirect short link to file download.

    Short links are stored in DynamoDB with session_id = 'file:{short_id}'.
    This avoids URL encoding issues with platforms like Feishu that encode
    underscores and other characters in URLs.

    Args:
        short_id: 8-character alphanumeric short link ID
    """
    settings = get_settings()

    # Validate short_id format (alphanumeric only)
    if not short_id.isalnum() or len(short_id) != 8:
        raise HTTPException(status_code=400, detail="Invalid short link format")

    # Look up in DynamoDB
    import boto3
    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    table = dynamodb.Table(settings.dynamodb_sessions_table)

    try:
        response = table.get_item(Key={"session_id": f"file:{short_id}"})
    except Exception as e:
        logger.error(f"DynamoDB lookup failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to look up short link")

    item = response.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Short link not found or expired")

    s3_key = item.get("s3_key")
    if not s3_key:
        raise HTTPException(status_code=500, detail="Invalid short link data")

    # Stream file directly (same as /files/stream)
    bucket = item.get("s3_bucket") or settings.code_interpreter_s3_bucket
    if not bucket:
        raise HTTPException(status_code=500, detail="S3 bucket not configured")

    from botocore.config import Config as BotoConfig
    s3_kwargs: dict = {
        "region_name": settings.aws_region,
        "config": BotoConfig(signature_version="s3v4"),
    }
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        s3_kwargs["aws_access_key_id"] = settings.aws_access_key_id
        s3_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    s3 = boto3.client("s3", **s3_kwargs)

    try:
        response = s3.get_object(Bucket=bucket, Key=s3_key)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail="File not found")
        logger.error(f"S3 get_object failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve file")

    # Get filename from DynamoDB item or extract from s3_key
    filename = item.get("filename") or s3_key.rsplit("/", 1)[-1]
    if "_" in filename and filename.split("_", 1)[0].isdigit():
        filename = filename.split("_", 1)[1]

    content_type = response.get("ContentType", "application/octet-stream")
    content_length = response.get("ContentLength")

    from urllib.parse import quote
    ascii_filename = filename.encode("ascii", "replace").decode("ascii")
    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"{ascii_filename}\"; "
            f"filename*=UTF-8''{quote(filename)}"
        ),
    }
    if content_length:
        headers["Content-Length"] = str(content_length)

    def stream_body():
        body = response["Body"]
        while chunk := body.read(64 * 1024):
            yield chunk

    return StreamingResponse(
        stream_body(),
        media_type=content_type,
        headers=headers,
    )


# ---- API Key Management ----

class GenerateApiKeyResponse(BaseModel):
    """Response from API key generation."""
    api_key: str
    message: str


class ApiKeyStatusResponse(BaseModel):
    """Response with API key authentication status."""
    auth_enabled: bool
    keys_configured: int
    message: str


@router.post("/api-keys/generate", response_model=GenerateApiKeyResponse)
async def generate_api_key() -> GenerateApiKeyResponse:
    """Generate a new MCP API key.
    
    The key is automatically added to the server configuration.
    Note: In production, keys should be stored securely (e.g., AWS Secrets Manager).
    """
    settings = get_settings()
    
    # Generate a secure random key
    new_key = f"sk-mcp-{secrets.token_hex(16)}"
    
    # Add to existing keys
    current_keys = list(settings.mcp_api_keys) if settings.mcp_api_keys else []
    current_keys.append(new_key)
    
    # Update settings (in-memory only - for persistent storage, use env vars or secrets manager)
    settings.mcp_api_keys = current_keys
    
    # Also enable auth if not already enabled
    if not settings.mcp_auth_enabled:
        settings.mcp_auth_enabled = True
        logger.info("MCP API key authentication has been enabled")
    
    logger.info("Generated new API key (total keys: %d)", len(current_keys))
    
    return GenerateApiKeyResponse(
        api_key=new_key,
        message=f"API key generated successfully. Total keys: {len(current_keys)}. "
                "Note: This key is stored in memory only. For persistence, add it to MCP_API_KEYS environment variable."
    )


@router.get("/api-keys/status", response_model=ApiKeyStatusResponse)
async def get_api_key_status() -> ApiKeyStatusResponse:
    """Get the current API key authentication status."""
    settings = get_settings()
    
    return ApiKeyStatusResponse(
        auth_enabled=settings.mcp_auth_enabled,
        keys_configured=len(settings.mcp_api_keys) if settings.mcp_api_keys else 0,
        message="API key authentication is " + ("enabled" if settings.mcp_auth_enabled else "disabled")
    )


class RevokeApiKeyRequest(BaseModel):
    """Request to revoke an API key."""
    api_key: str


@router.post("/api-keys/revoke")
async def revoke_api_key(req: RevokeApiKeyRequest) -> dict[str, str]:
    """Revoke an existing API key.
    
    Note: This only removes the key from memory. Update MCP_API_KEYS env var to persist the change.
    """
    settings = get_settings()
    
    current_keys = list(settings.mcp_api_keys) if settings.mcp_api_keys else []
    
    if req.api_key not in current_keys:
        raise HTTPException(status_code=404, detail="API key not found")
    
    current_keys.remove(req.api_key)
    settings.mcp_api_keys = current_keys
    
    logger.info("Revoked API key (remaining keys: %d)", len(current_keys))
    
    return {
        "message": f"API key revoked successfully. Remaining keys: {len(current_keys)}",
        "remaining_keys": str(len(current_keys))
    }


# ---- Authentication Configuration ----

class AuthConfigResponse(BaseModel):
    """Response with authentication configuration for frontend display."""
    auth_type: str  # 'cognito', 'api_key', or 'none'
    cognito_enabled: bool
    cognito_region: str | None = None
    cognito_user_pool_id: str | None = None
    token_endpoint: str | None = None
    client_id: str | None = None
    scopes: str | None = None
    mcp_server_url: str


@router.get("/auth-config", response_model=AuthConfigResponse)
async def get_auth_config() -> AuthConfigResponse:
    """Get authentication configuration for MCP integration.
    
    Returns OAuth 2.0 (Cognito S2S) configuration details that clients
    need to authenticate with the MCP server.
    
    Note: Client Secret is NOT returned for security reasons.
    Administrators should provide it separately through secure channels.
    """
    settings = get_settings()
    
    # Determine auth type
    if settings.cognito_enabled:
        auth_type = "cognito"
    elif settings.mcp_auth_enabled:
        auth_type = "api_key"
    else:
        auth_type = "none"
    
    # Build token endpoint URL if Cognito is enabled
    token_endpoint = None
    if settings.cognito_enabled and settings.cognito_user_pool_id:
        cognito_region = settings.cognito_region or settings.aws_region
        # Try to use configured token endpoint, or construct from user pool
        token_endpoint = settings.cognito_token_endpoint
        # Note: Domain prefix is not easily derivable, so we rely on configured endpoint
    
    return AuthConfigResponse(
        auth_type=auth_type,
        cognito_enabled=settings.cognito_enabled,
        cognito_region=settings.cognito_region or settings.aws_region,
        cognito_user_pool_id=settings.cognito_user_pool_id if settings.cognito_enabled else None,
        token_endpoint=token_endpoint,
        client_id=settings.cognito_client_id if settings.cognito_enabled else None,
        scopes=" ".join(settings.cognito_scopes_list) if settings.cognito_scopes_list else "openmcpskills-api/mcp openmcpskills-api/read",
        mcp_server_url=settings.mcp_server_url,
    )
