"""Service layer for events domain."""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.realtime.events.models import Event, RealtimeEvent
from ii_agent.realtime.events.publisher import EventPublisher, NoopEventPublisher
from ii_agent.realtime.events.repository import EventRepository

logger = logging.getLogger(__name__)


class EventService:
    """Service wrapping EventRepository for socket-layer usage."""

    def __init__(
        self,
        *,
        event_repo: EventRepository,
        config: Settings,
        publisher: EventPublisher | None = None,
    ) -> None:
        self._config = config
        self._repo = event_repo
        self._publisher = publisher or NoopEventPublisher()

    @staticmethod
    def _normalize_timestamp(event: RealtimeEvent) -> datetime:
        """Convert event timestamp to a timezone-aware UTC datetime."""
        if event.timestamp:
            return datetime.fromtimestamp(event.timestamp, tz=timezone.utc)
        return datetime.now(timezone.utc)

    async def save_event(
        self, db: AsyncSession, session_id: uuid.UUID, event: RealtimeEvent
    ) -> Event:
        created_at = self._normalize_timestamp(event)
        return await self._repo.save(db, session_id, event, created_at=created_at)

    async def emit_event(self, event: RealtimeEvent) -> None:
        try:
            await self._publisher.publish(event)
        except Exception as exc:
            logger.debug("Failed to emit realtime event: %s", exc)
