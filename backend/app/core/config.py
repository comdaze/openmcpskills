"""Application configuration using pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Open MCP Skills"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    log_level: str = "INFO"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Skills directory
    skills_dir: Path = Field(default=Path("./skills"))
    skills_watch_enabled: bool = True

    # Redis (for Pub/Sub and caching)
    redis_url: str = "redis://localhost:6379/0"
    redis_skills_channel: str = "mcp:skills:updates"

    # AWS Configuration
    aws_region: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    # DynamoDB
    dynamodb_endpoint_url: str | None = None
    dynamodb_skills_table: str = "mcp-skills"
    dynamodb_sessions_table: str = "mcp-sessions"

    # S3
    s3_endpoint_url: str | None = None
    s3_skills_bucket: str = "mcp-skills-bucket-383570952416"
    s3_skills_prefix: str = "skills/"

    # Storage backend
    storage_backend: Literal["local", "s3"] = "local"
    skill_cache_dir: Path = Field(default=Path("/tmp/skill-cache"))
    dynamodb_invocation_logs_table: str = "mcp-invocation-logs"
    invocation_log_ttl_days: int = 30

    # Authentication (AWS Cognito)
    cognito_enabled: bool = False
    cognito_user_pool_id: str | None = None
    cognito_client_id: str | None = None
    cognito_region: str | None = None

    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # Sandbox Configuration
    sandbox_enabled: bool = True
    sandbox_timeout_seconds: int = 30
    sandbox_memory_limit_mb: int = 512

    # LLM Configuration (for Agentic Tools)
    llm_provider: Literal["bedrock", "openai", "anthropic"] = "bedrock"
    llm_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    @property
    def skills_path(self) -> Path:
        """Get absolute path to skills directory."""
        return self.skills_dir.resolve()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
