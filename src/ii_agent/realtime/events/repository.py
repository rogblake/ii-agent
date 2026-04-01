"""Repository layer for events domain - data access only."""

from __future__ import annotations

import uuid
from typing import List

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db import BaseRepository
from ii_agent.realtime.events.models import ApplicationEvent


class EventRepository(BaseRepository[ApplicationEvent]):
    """Data access layer for ApplicationEvent."""

    model = ApplicationEvent

    async def get_by_session(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> List[ApplicationEvent]:
        """Get all events for a session ordered by creation time."""
        result = await db.execute(
            select(ApplicationEvent)
            .where(ApplicationEvent.session_id == session_id)
            .order_by(asc(ApplicationEvent.created_at))
        )
        return list(result.scalars().all())

    async def get_by_session_filtered(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        excluded_types: List[str] | None = None,
    ) -> List[ApplicationEvent]:
        """Get events for a session, optionally excluding certain types."""
        query = select(ApplicationEvent).where(ApplicationEvent.session_id == session_id)

        if excluded_types:
            query = query.where(ApplicationEvent.event_type.not_in(excluded_types))

        query = query.order_by(asc(ApplicationEvent.created_at))
        result = await db.execute(query)
        return list(result.scalars().all())
