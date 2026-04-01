"""Service layer for events domain — business logic for persisting realtime events."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.realtime.events.app_events import BaseEvent
from ii_agent.realtime.events.models import ApplicationEvent
from ii_agent.realtime.events.repository import EventRepository

if TYPE_CHECKING:
    from ii_agent.sessions.service import SessionService


class EventService:
    """Business logic for persisting realtime events."""

    def __init__(
        self,
        *,
        event_repo: EventRepository,
        session_service: SessionService,
    ) -> None:
        self._event_repo = event_repo
        self._session_service = session_service

    async def save_event(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        event: BaseEvent,
    ) -> ApplicationEvent:
        """Persist a realtime event and run post-save side-effects.

        Converts a :class:`BaseEvent` into an :class:`ApplicationEvent` row.
        On user messages, bumps ``session.updated_at`` so the session list
        stays sorted by recent activity.
        """
        db_event = ApplicationEvent(
            id=event.id,
            event_type=event.name,
            event_group=event.group,
            session_id=session_id,
            run_id=getattr(event, "run_id", None),
            user_id=event.user_id,
            content=event.content,
        )
        saved = await self._event_repo.save(db, db_event)

        if event.name == "session.user_message":
            await self._session_service.update_session_fields(
                db, session_id, updated_at=datetime.now(timezone.utc)
            )

        return saved
