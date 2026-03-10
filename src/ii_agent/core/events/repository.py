"""Repository layer for events domain - data access only."""

import uuid
from datetime import datetime, timezone
from typing import List

from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.events.models import Event, EventType, RealtimeEvent


class EventRepository:
    """Data access layer for Event model."""

    async def save(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        event: RealtimeEvent,
        *,
        created_at: datetime | None = None,
    ) -> Event:
        """Persist a RealtimeEvent as a database Event.

        Args:
            db: The async database session
            session_id: The session this event belongs to
            event: The realtime event to persist
            created_at: Pre-normalized timestamp (falls back to utcnow)

        Returns:
            The created Event ORM instance
        """
        event_timestamp = created_at or datetime.now(timezone.utc)

        db_event = Event(
            id=str(event.id),
            session_id=str(session_id),
            run_id=event.run_id,
            type=event.type.value,
            content=event.content,
            created_at=event_timestamp,
        )
        db.add(db_event)
        await db.flush()
        await db.refresh(db_event)
        return db_event

    async def get_by_session(self, db: AsyncSession, session_id: str | uuid.UUID) -> List[Event]:
        """Get all events for a session ordered by creation time.

        Args:
            db: The async database session
            session_id: The session ID

        Returns:
            List of events for the session
        """
        result = await db.execute(
            select(Event)
            .where(Event.session_id == str(session_id))
            .order_by(asc(Event.created_at))
        )
        return list(result.scalars().all())

    async def get_by_session_filtered(
        self,
        db: AsyncSession,
        session_id: str,
        excluded_types: List[str] | None = None,
    ) -> List[Event]:
        """Get events for a session, optionally excluding certain types.

        Args:
            db: The async database session
            session_id: The session ID
            excluded_types: Event type values to exclude

        Returns:
            Filtered list of events
        """
        query = select(Event).where(Event.session_id == session_id)

        if excluded_types:
            query = query.where(Event.type.not_in(excluded_types))

        query = query.order_by(asc(Event.created_at))
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_latest_by_type(
        self,
        db: AsyncSession,
        session_id: str,
        event_type: str,
    ) -> Event | None:
        """Get the latest event of a given type for a session.

        Args:
            db: The async database session
            session_id: The session ID
            event_type: The event type value to filter by

        Returns:
            The latest matching event, or None
        """
        result = await db.execute(
            select(Event)
            .where(Event.session_id == session_id)
            .where(Event.type == event_type)
            .order_by(desc(Event.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(self, db: AsyncSession, event: Event) -> Event:
        """Persist a raw Event ORM instance."""
        db.add(event)
        await db.flush()
        return event
