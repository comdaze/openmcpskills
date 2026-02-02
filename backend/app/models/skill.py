"""Skill data models following Claude Skills standard.

Based on the Agent Skills open standard specification:
https://agentskills.io/specification
"""

import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SkillStatus(str, Enum):
    """Status of a skill."""

    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class SkillHook(BaseModel):
    """Skill lifecycle hook definition."""

    event: str = Field(..., description="Hook event: PreToolUse, PostToolUse, Stop")
    command: str = Field(..., description="Command to execute")


class SkillMetadata(BaseModel):
    """Additional metadata for a skill."""

    author: str | None = Field(default=None, description="Skill author")
    version: str | None = Field(default=None, description="Skill version")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    extra: dict[str, str] = Field(default_factory=dict, description="Additional key-value pairs")


class SkillManifest(BaseModel):
    """Skill manifest following Claude Skills standard.

    This defines the metadata and instructions for a skill that follows
    the Agent Skills open standard specification.

    Required fields:
    - name: Unique identifier (lowercase, numbers, hyphens only)
    - description: What the skill does and when to use it

    Optional fields:
    - license: License name or reference
    - compatibility: Environment requirements
    - metadata: Additional properties (author, version, etc.)
    - allowed_tools: Pre-approved tools list
    - model: Specific Claude model to use
    - context: Set to 'fork' for isolated sub-agent context
    - user_invocable: Controls slash command visibility
    - hooks: Lifecycle hooks
    """

    # Required fields
    name: str = Field(
        ...,
        description="Unique skill identifier (lowercase letters, numbers, hyphens only)",
        max_length=64,
    )
    description: str = Field(
        ...,
        description="Detailed description of what the skill does and when to use it",
        max_length=1024,
    )

    # Optional fields
    license: str | None = Field(
        default=None,
        description="License name (e.g., Apache-2.0) or reference to license file"
    )
    compatibility: str | None = Field(
        default=None,
        description="Environment requirements, system packages, network access needs",
        max_length=500,
    )
    metadata: SkillMetadata = Field(
        default_factory=SkillMetadata,
        description="Additional metadata properties"
    )
    allowed_tools: list[str] = Field(
        default_factory=list,
        description="Pre-approved tools (e.g., ['Read', 'Grep', 'Bash(git:*)'])"
    )
    model: str | None = Field(
        default=None,
        description="Specific Claude model to use"
    )
    context: str | None = Field(
        default=None,
        description="Set to 'fork' for isolated sub-agent context"
    )
    user_invocable: bool = Field(
        default=True,
        description="Controls slash command menu visibility"
    )
    hooks: list[SkillHook] = Field(
        default_factory=list,
        description="Lifecycle hooks"
    )

    # Instructions (from SKILL.md body)
    instructions: str = Field(
        default="",
        description="Markdown instructions from SKILL.md body"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate skill name follows the standard.

        Rules:
        - Lowercase letters, numbers, and hyphens only
        - Cannot start or end with hyphen
        - No consecutive hyphens
        - Max 64 characters
        """
        if not v:
            raise ValueError("Name cannot be empty")

        # Check for valid characters
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError(
                "Name must contain only lowercase letters, numbers, and hyphens"
            )

        # Cannot start or end with hyphen
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("Name cannot start or end with a hyphen")

        # No consecutive hyphens
        if "--" in v:
            raise ValueError("Name cannot contain consecutive hyphens")

        return v

    def to_mcp_tool(self) -> dict[str, Any]:
        """Convert to MCP Tool format for tools/list response."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": {
                    "arguments": {
                        "type": "string",
                        "description": "Arguments to pass to the skill ($ARGUMENTS)",
                    },
                },
                "required": [],
            },
        }


class Skill(BaseModel):
    """Full skill model with manifest and runtime state."""

    id: str = Field(..., description="Unique skill ID (same as manifest.name)")
    manifest: SkillManifest = Field(..., description="Skill manifest from SKILL.md")
    status: SkillStatus = Field(default=SkillStatus.DRAFT, description="Current status")

    # Source information
    source_path: str | None = Field(default=None, description="Local directory path")
    skill_md_path: str | None = Field(default=None, description="Path to SKILL.md")

    # Additional files
    reference_files: list[str] = Field(
        default_factory=list,
        description="List of reference file paths"
    )
    script_files: list[str] = Field(
        default_factory=list,
        description="List of script file paths"
    )
    asset_files: list[str] = Field(
        default_factory=list,
        description="List of asset file paths"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Runtime state
    load_error: str | None = Field(default=None, description="Error message if loading failed")
    invocation_count: int = Field(default=0, description="Number of times invoked")
    last_invoked_at: datetime | None = Field(default=None)

    class Config:
        """Pydantic config."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

    def get_full_instructions(self) -> str:
        """Get the full instructions including referenced files."""
        return self.manifest.instructions

    def is_user_invocable(self) -> bool:
        """Check if skill can be invoked via slash command."""
        return self.manifest.user_invocable
