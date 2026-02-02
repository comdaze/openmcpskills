"""Redis Pub/Sub service for skill synchronization.

Enables multiple server instances to stay synchronized
when skills are added, updated, or removed.
"""

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Callable

import redis.asyncio as redis

from app.core.config import get_settings
from app.services.skill_loader import SkillLoader

logger = logging.getLogger(__name__)


class SkillEventType(str, Enum):
    """Types of skill-related events."""

    LOADED = "skill:loaded"
    UNLOADED = "skill:unloaded"
    UPDATED = "skill:updated"
    RELOAD_ALL = "skill:reload_all"


class SkillEvent:
    """A skill synchronization event."""

    def __init__(
        self,
        event_type: SkillEventType,
        skill_id: str | None = None,
        source_instance: str | None = None,
        timestamp: datetime | None = None,
        data: dict[str, Any] | None = None,
    ):
        self.event_type = event_type
        self.skill_id = skill_id
        self.source_instance = source_instance
        self.timestamp = timestamp or datetime.utcnow()
        self.data = data or {}

    def to_json(self) -> str:
        """Serialize event to JSON."""
        return json.dumps({
            "event_type": self.event_type.value,
            "skill_id": self.skill_id,
            "source_instance": self.source_instance,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        })

    @classmethod
    def from_json(cls, data: str) -> "SkillEvent":
        """Deserialize event from JSON."""
        parsed = json.loads(data)
        return cls(
            event_type=SkillEventType(parsed["event_type"]),
            skill_id=parsed.get("skill_id"),
            source_instance=parsed.get("source_instance"),
            timestamp=datetime.fromisoformat(parsed["timestamp"]),
            data=parsed.get("data", {}),
        )


class RedisSyncService:
    """Redis-based skill synchronization service.

    Uses Pub/Sub to broadcast skill changes across
    multiple server instances in an ECS cluster.
    """

    def __init__(
        self,
        skill_loader: SkillLoader,
        instance_id: str | None = None,
    ) -> None:
        self._skill_loader = skill_loader
        self._settings = get_settings()
        self._instance_id = instance_id or self._generate_instance_id()
        self._redis: redis.Redis | None = None
        self._pubsub: redis.client.PubSub | None = None
        self._listener_task: asyncio.Task[None] | None = None
        self._connected = False
        self._event_handlers: list[Callable[[SkillEvent], None]] = []

    def _generate_instance_id(self) -> str:
        """Generate a unique instance ID."""
        import uuid
        return f"mcp-{uuid.uuid4().hex[:8]}"

    @property
    def instance_id(self) -> str:
        """Get the instance ID."""
        return self._instance_id

    @property
    def channel(self) -> str:
        """Get the Redis channel name."""
        return self._settings.redis_skills_channel

    def add_event_handler(self, handler: Callable[[SkillEvent], None]) -> None:
        """Add a handler for skill events."""
        self._event_handlers.append(handler)

    async def connect(self) -> bool:
        """Connect to Redis."""
        try:
            self._redis = redis.from_url(
                self._settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )

            # Test connection
            await self._redis.ping()
            self._connected = True
            logger.info(f"Connected to Redis: {self._settings.redis_url}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._pubsub:
            await self._pubsub.unsubscribe(self.channel)
            await self._pubsub.close()
            self._pubsub = None

        if self._redis:
            await self._redis.close()
            self._redis = None

        self._connected = False
        logger.info("Disconnected from Redis")

    async def start_listener(self) -> None:
        """Start listening for skill events."""
        if not self._redis:
            if not await self.connect():
                return

        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(self.channel)

        self._listener_task = asyncio.create_task(self._listen_loop())
        logger.info(f"Started Redis listener on channel: {self.channel}")

    async def stop_listener(self) -> None:
        """Stop the event listener."""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        logger.info("Stopped Redis listener")

    async def _listen_loop(self) -> None:
        """Main listener loop for Redis Pub/Sub."""
        if not self._pubsub:
            return

        try:
            async for message in self._pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    event = SkillEvent.from_json(message["data"])

                    # Skip events from our own instance
                    if event.source_instance == self._instance_id:
                        continue

                    logger.debug(
                        f"Received event: {event.event_type} "
                        f"from {event.source_instance}"
                    )

                    await self._handle_event(event)

                except Exception as e:
                    logger.error(f"Error processing event: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Redis listener error: {e}")

    async def _handle_event(self, event: SkillEvent) -> None:
        """Handle a received skill event."""
        if event.event_type == SkillEventType.RELOAD_ALL:
            # Reload all skills
            await self._skill_loader.load_from_directory()

        elif event.event_type == SkillEventType.LOADED:
            # Another instance loaded a skill - reload if we have it
            if event.skill_id:
                await self._skill_loader.reload_skill(event.skill_id)

        elif event.event_type == SkillEventType.UNLOADED:
            # Another instance unloaded a skill
            if event.skill_id:
                await self._skill_loader.unload_skill(event.skill_id)

        elif event.event_type == SkillEventType.UPDATED:
            # Another instance updated a skill - reload it
            if event.skill_id:
                await self._skill_loader.reload_skill(event.skill_id)

        # Notify custom handlers
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")

    async def publish_event(self, event: SkillEvent) -> bool:
        """Publish a skill event to other instances."""
        if not self._redis or not self._connected:
            logger.warning("Cannot publish event: not connected to Redis")
            return False

        event.source_instance = self._instance_id

        try:
            await self._redis.publish(self.channel, event.to_json())
            logger.debug(f"Published event: {event.event_type}")
            return True

        except Exception as e:
            logger.error(f"Failed to publish event: {e}")
            return False

    async def notify_skill_loaded(self, skill_id: str) -> bool:
        """Notify other instances that a skill was loaded."""
        event = SkillEvent(
            event_type=SkillEventType.LOADED,
            skill_id=skill_id,
        )
        return await self.publish_event(event)

    async def notify_skill_unloaded(self, skill_id: str) -> bool:
        """Notify other instances that a skill was unloaded."""
        event = SkillEvent(
            event_type=SkillEventType.UNLOADED,
            skill_id=skill_id,
        )
        return await self.publish_event(event)

    async def notify_skill_updated(self, skill_id: str) -> bool:
        """Notify other instances that a skill was updated."""
        event = SkillEvent(
            event_type=SkillEventType.UPDATED,
            skill_id=skill_id,
        )
        return await self.publish_event(event)

    async def notify_reload_all(self) -> bool:
        """Notify all instances to reload all skills."""
        event = SkillEvent(event_type=SkillEventType.RELOAD_ALL)
        return await self.publish_event(event)
