"""Application configuration using pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
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

    # Authentication (AWS Cognito S2S)
    cognito_enabled: bool = False
    cognito_user_pool_id: str | None = None
    cognito_client_id: str | None = None  # App client ID for this service (if acting as client)
    cognito_allowed_client_ids: str = ""  # Comma-separated allowed client IDs for incoming requests
    cognito_region: str | None = None
    cognito_token_endpoint: str | None = None  # OAuth2 token endpoint
    cognito_discovery_url: str | None = None  # OpenID Connect discovery URL
    cognito_resource_server: str | None = None  # Resource server identifier
    cognito_scopes: str = ""  # Comma-separated required scopes for access

    @property
    def cognito_allowed_client_ids_list(self) -> list[str]:
        """Get allowed client IDs as list."""
        if not self.cognito_allowed_client_ids:
            return []
        return [k.strip() for k in self.cognito_allowed_client_ids.split(",") if k.strip()]

    @property
    def cognito_scopes_list(self) -> list[str]:
        """Get scopes as list."""
        if not self.cognito_scopes:
            return []
        return [k.strip() for k in self.cognito_scopes.split(",") if k.strip()]

    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # MCP API Key Authentication
    mcp_auth_enabled: bool = False  # Enable in production
    mcp_api_keys: str = ""  # Comma-separated in env: "key1,key2,key3"

    @property
    def mcp_api_keys_list(self) -> list[str]:
        """Get API keys as list."""
        if not self.mcp_api_keys:
            return []
        return [k.strip() for k in self.mcp_api_keys.split(",") if k.strip()]

    # Sandbox Configuration
    sandbox_enabled: bool = True
    sandbox_timeout_seconds: int = 30
    sandbox_memory_limit_mb: int = 512

    # LLM Configuration (for Agentic Tools)
    llm_provider: Literal["bedrock", "openai", "anthropic"] = "bedrock"
    llm_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # Playground Configuration
    mcp_server_url: str = "https://mcp.openmcpskills.click/mcp"
    bedrock_endpoint: str | None = None
    bedrock_api_key: str | None = None
    
    # Claude Model IDs
    claude_opus_4_6_model_id: str = "us.anthropic.claude-opus-4-6-v1"
    claude_opus_model_id: str = "us.anthropic.claude-opus-4-5-20251101-v1:0"
    claude_sonnet_model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    claude_haiku_model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

    # AgentCore Code Interpreter Configuration
    code_interpreter_enabled: bool = False
    code_interpreter_id: str = "aws.codeinterpreter.v1"
    code_interpreter_default_timeout: int = 300
    code_interpreter_session_timeout: int = 900
    code_interpreter_s3_bucket: str = ""
    code_interpreter_s3_prefix: str = "output_artifacts/"

    @property
    def skills_path(self) -> Path:
        """Get absolute path to skills directory."""
        return self.skills_dir.resolve()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
