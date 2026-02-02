"""Session management for MCP connections.

Manages client sessions including state, capabilities, and cleanup.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from app.models.session import Session, SessionState

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages MCP client sessions.

    Handles:
    - Session creation and lifecycle
    - Capability negotiation
    - Session expiration and cleanup
    - Request routing
    """

    def __init__(
        self,
        session_timeout_minutes: int = 60,
        cleanup_interval_seconds: int = 300,
    ) -> None:
        self._sessions: dict[str, Session] = {}
        self._session_timeout = timedelta(minutes=session_timeout_minutes)
        self._cleanup_interval = cleanup_interval_seconds
        self._cleanup_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the session manager and cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Session manager started")

    async def stop(self) -> None:
        """Stop the session manager and cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Session manager stopped")

    async def create_session(
        self,
        client_name: str | None = None,
        client_version: str | None = None,
        user_id: str | None = None,
    ) -> Session:
        """Create a new session."""
        async with self._lock:
            session_id = str(uuid.uuid4())
            expires_at = datetime.utcnow() + self._session_timeout

            session = Session(
                id=session_id,
                state=SessionState.INITIALIZING,
                client_name=client_name,
                client_version=client_version,
                user_id=user_id,
                expires_at=expires_at,
            )

            self._sessions[session_id] = session
            logger.debug(f"Created session: {session_id}")
            return session

    async def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        session = self._sessions.get(session_id)
        if session and session.is_expired():
            await self.close_session(session_id)
            return None
        return session

    async def activate_session(
        self,
        session_id: str,
        client_capabilities: dict[str, Any],
        server_capabilities: dict[str, Any],
    ) -> bool:
        """Activate a session after successful initialization."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False

            session.state = SessionState.ACTIVE
            session.client_capabilities = client_capabilities
            session.server_capabilities = server_capabilities
            session.update_activity()

            logger.debug(f"Activated session: {session_id}")
            return True

    async def close_session(self, session_id: str) -> bool:
        """Close and remove a session."""
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                session.state = SessionState.CLOSED
                logger.debug(f"Closed session: {session_id}")
                return True
            return False

    async def update_activity(self, session_id: str) -> bool:
        """Update session last activity timestamp."""
        session = self._sessions.get(session_id)
        if session:
            session.update_activity()
            return True
        return False

    async def set_pending_request(
        self,
        session_id: str,
        request_id: str,
        request_data: dict[str, Any],
    ) -> bool:
        """Track a pending request for streaming response."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.pending_requests[request_id] = {
            "data": request_data,
            "started_at": datetime.utcnow().isoformat(),
        }
        session.last_request_id = request_id
        return True

    async def complete_request(
        self,
        session_id: str,
        request_id: str,
    ) -> bool:
        """Mark a pending request as complete."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.pending_requests.pop(request_id, None)
        return True

    def get_active_session_count(self) -> int:
        """Get count of active sessions."""
        return sum(1 for s in self._sessions.values() if s.is_active())

    def get_all_sessions(self) -> list[Session]:
        """Get all sessions for admin dashboard."""
        return list(self._sessions.values())

    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired sessions."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Session cleanup error: {e}")

    async def _cleanup_expired(self) -> None:
        """Remove expired sessions."""
        async with self._lock:
            expired = [
                sid for sid, session in self._sessions.items()
                if session.is_expired()
            ]

            for session_id in expired:
                del self._sessions[session_id]
                logger.debug(f"Cleaned up expired session: {session_id}")

            if expired:
                logger.info(f"Cleaned up {len(expired)} expired sessions")
