"""Dynamic skill loading service for Claude Skills standard.

Handles loading skills from the local filesystem following the
Agent Skills open standard specification (SKILL.md format).
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Callable

import yaml

from app.core.config import get_settings
from app.models.skill import Skill, SkillManifest, SkillMetadata, SkillHook, SkillExecution, SkillStatus

logger = logging.getLogger(__name__)

# SKILL.md file name (case-sensitive)
SKILL_MD_FILENAME = "SKILL.md"

# Standard directories in a skill package
SCRIPTS_DIR = "scripts"
REFERENCES_DIR = "references"
ASSETS_DIR = "assets"


class SkillParseError(Exception):
    """Error parsing a skill's SKILL.md file."""

    pass


class SkillLoader:
    """Loads and manages Claude Skills.

    Supports loading skills that follow the Agent Skills standard:
    - Each skill is a directory containing SKILL.md
    - SKILL.md has YAML frontmatter and Markdown body
    - Optional scripts/, references/, and assets/ directories
    
    Implements lazy loading: only metadata is loaded at startup,
    full skill content is loaded on first access.
    """

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        self._skill_paths: dict[str, Path] = {}  # skill_id -> directory path
        self._load_lock = asyncio.Lock()
        self._settings = get_settings()
        self._watchers: list[Callable[[str, str], None]] = []

    @property
    def skills(self) -> dict[str, Skill]:
        """Get all loaded skills."""
        return self._skills.copy()

    @property
    def all_skill_ids(self) -> list[str]:
        """Get IDs of all registered skills (loaded + lazy)."""
        return list(set(self._skills.keys()) | set(self._skill_paths.keys()))

    @property
    def active_skills(self) -> dict[str, Skill]:
        """Get only active skills."""
        return {
            k: v for k, v in self._skills.items()
            if v.status == SkillStatus.ACTIVE
        }

    async def get_skill(self, skill_id: str) -> Skill | None:
        """Get a skill by ID, loading it on-demand if needed."""
        if skill_id in self._skills:
            return self._skills[skill_id]
        
        # Try to load on-demand
        if skill_id in self._skill_paths:
            return await self.load_skill(self._skill_paths[skill_id])
        
        return None

    def add_watcher(self, callback: Callable[[str, str], None]) -> None:
        """Add a watcher for skill changes.

        Callback receives (skill_id, event_type) where event_type is
        'loaded', 'unloaded', 'updated', or 'error'.
        """
        self._watchers.append(callback)

    def _notify_watchers(self, skill_id: str, event_type: str) -> None:
        """Notify all watchers of a skill change."""
        for watcher in self._watchers:
            try:
                watcher(skill_id, event_type)
            except Exception as e:
                logger.error(f"Watcher error: {e}")

    async def load_from_directory(self, directory: Path | None = None, lazy: bool = True) -> int:
        """Load skills from a directory.

        Args:
            directory: Directory containing skill subdirectories
            lazy: If True, only load metadata; full content loaded on first access
        
        Returns the number of skills discovered.
        """
        if directory is None:
            directory = self._settings.skills_path

        if not directory.exists():
            logger.warning(f"Skills directory does not exist: {directory}")
            directory.mkdir(parents=True, exist_ok=True)
            return 0

        discovered_count = 0
        for skill_dir in directory.iterdir():
            if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                continue

            try:
                if lazy:
                    # Only register the path, don't load yet
                    skill_md_path = skill_dir / SKILL_MD_FILENAME
                    if skill_md_path.exists():
                        manifest = self._parse_skill_metadata_only(skill_md_path)
                        skill_id = manifest.name
                        self._skill_paths[skill_id] = skill_dir
                        discovered_count += 1
                        logger.debug(f"Registered skill: {manifest.name}")
                else:
                    # Full load
                    skill = await self.load_skill(skill_dir)
                    if skill:
                        discovered_count += 1
                        logger.info(f"Loaded skill: {skill.manifest.name}")
            except Exception as e:
                logger.error(f"Failed to process skill from {skill_dir}: {e}")

        return discovered_count

    async def load_skill(self, skill_path: Path) -> Skill | None:
        """Load a single skill from a directory."""
        async with self._load_lock:
            # Find SKILL.md
            skill_md_path = skill_path / SKILL_MD_FILENAME
            if not skill_md_path.exists():
                logger.warning(f"No SKILL.md found in {skill_path}")
                return None

            # Parse SKILL.md
            try:
                manifest = self._parse_skill_md(skill_md_path)
            except SkillParseError as e:
                logger.error(f"Failed to parse {skill_md_path}: {e}")
                return None

            # Validate directory name matches skill name
            if skill_path.name != manifest.name:
                logger.warning(
                    f"Directory name '{skill_path.name}' doesn't match "
                    f"skill name '{manifest.name}'. Using skill name."
                )

            # Create skill object
            skill_id = manifest.name
            skill = Skill(
                id=skill_id,
                manifest=manifest,
                source_path=str(skill_path),
                skill_md_path=str(skill_md_path),
                status=SkillStatus.ACTIVE,
            )

            # Set version from S3 marker if available
            version_file = skill_path / ".current_version"
            if version_file.exists():
                skill.manifest.metadata.version = version_file.read_text().strip()

            # Discover additional files
            skill.script_files = self._discover_files(skill_path / SCRIPTS_DIR)
            skill.reference_files = self._discover_files(skill_path / REFERENCES_DIR)
            skill.asset_files = self._discover_files(skill_path / ASSETS_DIR)

            # Store skill
            old_skill = self._skills.get(skill_id)
            self._skills[skill_id] = skill

            # Notify watchers
            event = "updated" if old_skill else "loaded"
            self._notify_watchers(skill_id, event)

            return skill

    async def unload_skill(self, skill_id: str) -> bool:
        """Unload a skill by ID."""
        async with self._load_lock:
            if skill_id not in self._skills:
                return False

            del self._skills[skill_id]
            self._notify_watchers(skill_id, "unloaded")
            return True

    async def reload_skill(self, skill_id: str, s3_store=None) -> Skill | None:
        """Reload a skill by ID.
        
        If s3_store is provided and storage backend is S3, downloads latest version from S3 first.
        Otherwise reloads from local cache.
        """
        settings = get_settings()
        
        # If using S3 storage, download latest version first
        if s3_store and settings.storage_backend == "s3":
            try:
                logger.info(f"Downloading latest version of {skill_id} from S3...")
                local_path = await s3_store.download_skill(skill_id)
                logger.info(f"Downloaded {skill_id} to {local_path}")
                # Load from downloaded path
                return await self.load_skill(local_path)
            except Exception as e:
                logger.error(f"Failed to download {skill_id} from S3: {e}")
                # Fall back to local cache
        
        # Reload from local cache
        skill = self._skills.get(skill_id)
        if not skill or not skill.source_path:
            return None

        return await self.load_skill(Path(skill.source_path))

    def _parse_skill_metadata_only(self, skill_md_path: Path) -> SkillManifest:
        """Parse only the frontmatter of SKILL.md for lazy loading.
        
        Returns a minimal SkillManifest with just name and description.
        Full parsing happens on first access.
        """
        content = skill_md_path.read_text(encoding="utf-8")
        frontmatter, _ = self._split_frontmatter(content)
        
        if not frontmatter:
            raise SkillParseError("SKILL.md must have YAML frontmatter")
        
        try:
            data = yaml.safe_load(frontmatter)
        except yaml.YAMLError as e:
            raise SkillParseError(f"Invalid YAML frontmatter: {e}")
        
        if not isinstance(data, dict):
            raise SkillParseError("Frontmatter must be a YAML mapping")
        
        # Only extract minimal required fields
        if "name" not in data or "description" not in data:
            raise SkillParseError("Missing required fields: name, description")
        
        return SkillManifest(
            name=data["name"],
            description=data["description"],
            instructions="",  # Will be loaded on-demand
        )

    def _parse_skill_md(self, skill_md_path: Path) -> SkillManifest:
        """Parse a SKILL.md file into a SkillManifest.

        SKILL.md format:
        ---
        name: skill-name
        description: What the skill does
        ... other YAML fields ...
        ---

        # Skill Title

        Markdown instructions...
        """
        content = skill_md_path.read_text(encoding="utf-8")

        # Split frontmatter and body
        frontmatter, body = self._split_frontmatter(content)

        if not frontmatter:
            raise SkillParseError("SKILL.md must have YAML frontmatter")

        # Parse YAML frontmatter
        try:
            data = yaml.safe_load(frontmatter)
        except yaml.YAMLError as e:
            raise SkillParseError(f"Invalid YAML frontmatter: {e}")

        if not isinstance(data, dict):
            raise SkillParseError("Frontmatter must be a YAML mapping")

        # Validate required fields
        if "name" not in data:
            raise SkillParseError("Missing required field: name")
        if "description" not in data:
            raise SkillParseError("Missing required field: description")

        # Parse metadata
        metadata_data = data.pop("metadata", {})
        if isinstance(metadata_data, dict):
            metadata = SkillMetadata(
                author=metadata_data.get("author"),
                version=metadata_data.get("version"),
                tags=metadata_data.get("tags", []),
                extra={
                    k: v for k, v in metadata_data.items()
                    if k not in ["author", "version", "tags"]
                },
            )
        else:
            metadata = SkillMetadata()

        # Parse hooks
        hooks_data = data.pop("hooks", [])
        hooks = []
        if isinstance(hooks_data, list):
            for hook_data in hooks_data:
                if isinstance(hook_data, dict):
                    hooks.append(SkillHook(
                        event=hook_data.get("event", ""),
                        command=hook_data.get("command", ""),
                    ))

        # Parse allowed-tools (can be string or list)
        allowed_tools_data = data.pop("allowed-tools", data.pop("allowed_tools", []))
        if isinstance(allowed_tools_data, str):
            # Space or comma delimited
            allowed_tools = [
                t.strip() for t in re.split(r"[,\s]+", allowed_tools_data)
                if t.strip()
            ]
        elif isinstance(allowed_tools_data, list):
            allowed_tools = allowed_tools_data
        else:
            allowed_tools = []

        # Handle user-invocable (can be "user-invocable" or "user_invocable")
        user_invocable = data.pop(
            "user-invocable",
            data.pop("user_invocable", True)
        )

        # Parse execution configuration
        execution_data = data.pop("execution", {})
        if isinstance(execution_data, dict):
            execution = SkillExecution(
                type=execution_data.get("type", "instruction"),
                runtime=execution_data.get("runtime", "python"),
                entrypoint=execution_data.get("entrypoint"),
                timeout=execution_data.get("timeout", 300),
                network=execution_data.get("network", "sandbox"),
                dependencies=execution_data.get("dependencies", []),
            )
        else:
            execution = SkillExecution()

        # Create manifest
        try:
            manifest = SkillManifest(
                name=data.pop("name"),
                description=data.pop("description"),
                license=data.pop("license", None),
                compatibility=data.pop("compatibility", None),
                metadata=metadata,
                allowed_tools=allowed_tools,
                model=data.pop("model", None),
                context=data.pop("context", None),
                user_invocable=user_invocable,
                hooks=hooks,
                execution=execution,
                instructions=body.strip(),
            )
        except ValueError as e:
            raise SkillParseError(f"Invalid manifest: {e}")

        return manifest

    def _split_frontmatter(self, content: str) -> tuple[str, str]:
        """Split SKILL.md into frontmatter and body.

        Returns (frontmatter, body) tuple.
        Frontmatter is between --- markers.
        """
        # Check for frontmatter
        if not content.startswith("---"):
            return "", content

        # Find the closing ---
        lines = content.split("\n")
        end_index = -1

        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_index = i
                break

        if end_index == -1:
            return "", content

        frontmatter = "\n".join(lines[1:end_index])
        body = "\n".join(lines[end_index + 1:])

        return frontmatter, body

    def _discover_files(self, directory: Path) -> list[str]:
        """Discover files in a directory."""
        if not directory.exists():
            return []

        files = []
        for file_path in directory.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith("."):
                files.append(str(file_path))

        return files

    async def validate_skill_package(self, package_path: Path) -> tuple[bool, str]:
        """Validate a skill package meets the Claude Skills standard.

        Checks:
        - Has SKILL.md file
        - SKILL.md has valid frontmatter
        - Required fields (name, description) are present
        - Name follows naming convention

        Returns (is_valid, message).
        """
        # Check SKILL.md exists
        skill_md_path = package_path / SKILL_MD_FILENAME
        if not skill_md_path.exists():
            return False, f"Missing required file: {SKILL_MD_FILENAME}"

        # Try to parse it
        try:
            manifest = self._parse_skill_md(skill_md_path)
        except SkillParseError as e:
            return False, str(e)

        # Check directory name matches skill name
        if package_path.name != manifest.name:
            return False, (
                f"Directory name '{package_path.name}' must match "
                f"skill name '{manifest.name}'"
            )

        # Check instructions aren't empty
        if not manifest.instructions.strip():
            return False, "SKILL.md body (instructions) cannot be empty"

        return True, "Valid Claude Skill package"

    def get_skill_instructions(self, skill_id: str) -> str | None:
        """Get the full instructions for a skill.

        This includes the main instructions from SKILL.md and can
        optionally include referenced files.
        """
        skill = self._skills.get(skill_id)
        if not skill:
            return None

        return skill.get_full_instructions()
