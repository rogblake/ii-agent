"""Service for managing session pins."""

from __future__ import annotations

import logging
import uuid
from typing import List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.sessions.repository import SessionRepository
from ii_agent.sessions.pin.models import SessionPin
from ii_agent.sessions.pin.repository import PinRepository
from ii_agent.sessions.pin.schemas import SessionPinItem

logger = logging.getLogger(__name__)


class SessionPinService:
    """Service for managing session pins."""

    def __init__(
        self,
        *,
        pin_repo: PinRepository,
        session_repo: SessionRepository,
        config: Settings,
    ) -> None:
        self._config = config
        self._pin_repo = pin_repo
        self._session_repo = session_repo

    async def get_user_pins(self, db: AsyncSession, user_id: uuid.UUID) -> List[SessionPinItem]:
        """Get all pinned sessions for a user."""
        pins = await self._pin_repo.get_user_pins(db, user_id)

        return [
            SessionPinItem(
                id=p.id,
                session_id=p.session_id,
                session_name=p.session.name,
                agent_type=p.session.agent_type,
                created_at=p.created_at,
                session_created_at=p.session.created_at,
                last_message_at=p.session.last_message_at,
            )
            for p in pins
            if p.session is not None and not p.session.is_deleted
        ]

    async def pin_session(self, db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
        """Pin a session for the user.

        Returns True if pinned successfully, False if already pinned.
        Raises SessionNotFoundError if session doesn't exist or user doesn't have access.
        """
        session = await self._session_repo.get_by_id_and_user(db, session_id, user_id)

        if not session:
            raise SessionNotFoundError(f"Session {session_id} not found or access denied")

        existing = await self._pin_repo.get_by_user_and_session(db, user_id, session_id)
        if existing:
            return False

        try:
            async with db.begin_nested():
                pin_item = SessionPin(user_id=user_id, session_id=session_id)
                await self._pin_repo.create(db, pin_item)
            return True
        except IntegrityError:
            # Concurrent request already created the pin; only the
            # savepoint is rolled back, the outer session stays valid.
            return False

    async def unpin_session(self, db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
        """Unpin a session for the user.

        Returns True if unpinned, False if not found.
        """
        return await self._pin_repo.delete_by_user_and_session(db, user_id, session_id)

    async def is_pinned(self, db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
        """Check if a session is pinned by the user."""
        item = await self._pin_repo.get_by_user_and_session(db, user_id, session_id)
        return item is not None
