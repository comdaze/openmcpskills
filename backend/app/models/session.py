"""Session management models for MCP connections."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SessionState(str, Enum):
    """State of an MCP session."""

    INITIALIZING = "initializing"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class Session(BaseModel):
    """MCP session tracking model.

    Tracks the state of a client connection including
    authentication, capabilities, and request routing.
    """

    id: str = Field(..., description="Unique session ID")
    state: SessionState = Field(default=SessionState.INITIALIZING)

    # Client information
    client_name: str | None = Field(default=None, description="MCP client name")
    client_version: str | None = Field(default=None, description="MCP client version")
    protocol_version: str = Field(default="2025-11-25", description="MCP protocol version")

    # Authentication
    user_id: str | None = Field(default=None, description="Authenticated user ID")
    auth_token: str | None = Field(default=None, description="Session auth token")
    scopes: list[str] = Field(default_factory=list, description="Authorized scopes")

    # Capabilities negotiated during initialization
    client_capabilities: dict[str, Any] = Field(
        default_factory=dict,
        description="Client capabilities from initialize request"
    )
    server_capabilities: dict[str, Any] = Field(
        default_factory=dict,
        description="Server capabilities sent to client"
    )

    # Request tracking
    last_request_id: str | None = Field(default=None)
    pending_requests: dict[str, Any] = Field(
        default_factory=dict,
        description="Pending request tracking for streaming responses"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = Field(default=None)

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if session has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def is_active(self) -> bool:
        """Check if session is active and not expired."""
        return self.state == SessionState.ACTIVE and not self.is_expired()

    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity_at = datetime.utcnow()

    class Config:
        """Pydantic config."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
