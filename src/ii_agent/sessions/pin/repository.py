"""Repository layer for session pins - data access only."""

import uuid
from typing import List, Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ii_agent.core.db.repository import BaseRepository
from ii_agent.sessions.pin.models import SessionPin


class PinRepository(BaseRepository[SessionPin]):
    """Data access layer for SessionPin model."""

    model = SessionPin

    async def get_user_pins(self, db: AsyncSession, user_id: uuid.UUID) -> List[SessionPin]:
        """Get all pin items for a user with session eager-loaded."""
        result = await db.execute(
            select(SessionPin)
            .options(selectinload(SessionPin.session))
            .where(SessionPin.user_id == user_id)
            .order_by(SessionPin.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_user_and_session(
        self, db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
    ) -> Optional[SessionPin]:
        """Get a pin item by user and session."""
        result = await db.execute(
            select(SessionPin).where(
                and_(
                    SessionPin.user_id == user_id,
                    SessionPin.session_id == session_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def create(self, db: AsyncSession, pin_item: SessionPin) -> SessionPin:
        """Persist a new pin item (no refresh needed)."""
        db.add(pin_item)
        await db.flush()
        return pin_item

    async def delete_by_user_and_session(
        self, db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
    ) -> bool:
        """Delete a pin item by user and session. Returns True if deleted."""
        result = await db.execute(
            delete(SessionPin).where(
                and_(
                    SessionPin.user_id == user_id,
                    SessionPin.session_id == session_id,
                )
            )
        )
        return result.rowcount > 0
