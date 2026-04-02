"""Service for managing session wishlists."""

from __future__ import annotations

import logging
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession


from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.sessions.repository import SessionRepository
from ii_agent.sessions.wishlist.models import SessionWishlist
from ii_agent.sessions.wishlist.repository import WishlistRepository

logger = logging.getLogger(__name__)


class SessionWishlistService:
    """Service for managing session wishlists."""

    def __init__(
        self,
        *,
        wishlist_repo: WishlistRepository,
        session_repo: SessionRepository,
        config: Settings,
    ) -> None:
        self._config = config
        self._wishlist_repo = wishlist_repo
        self._session_repo = session_repo

    async def get_user_wishlist(self, db: AsyncSession, user_id: str) -> List[dict]:
        """Get all wishlist sessions for a user."""
        wishlists = await self._wishlist_repo.get_user_wishlists(db, user_id)

        return [
            {
                "id": w.id,
                "session_id": w.session_id,
                "session_name": w.session.name if w.session else None,
                "created_at": w.created_at,
                "last_message_at": w.session.last_message_at if w.session else None,
            }
            for w in wishlists
        ]

    async def add_to_wishlist(self, db: AsyncSession, user_id: str, session_id: str) -> bool:
        """Add a session to user's wishlist.

        Returns True if added successfully, False if already exists.
        Raises ValueError if session doesn't exist or user doesn't have access.
        """
        # Check if the session exists and user has access
        session = await self._session_repo.get_by_id(db, session_id)

        if not session or session.user_id != user_id:
            raise SessionNotFoundError(f"Session {session_id} not found or access denied")

        # Check if already in wishlist
        existing = await self._wishlist_repo.get_by_user_and_session(db, user_id, session_id)
        if existing:
            return False

        wishlist_item = SessionWishlist(user_id=user_id, session_id=session_id)
        await self._wishlist_repo.create(db, wishlist_item)
        return True

    async def remove_from_wishlist(self, db: AsyncSession, user_id: str, session_id: str) -> bool:
        """Remove a session from user's wishlist.

        Returns True if removed, False if not found.
        """
        return await self._wishlist_repo.delete_by_user_and_session(db, user_id, session_id)

    async def is_in_wishlist(self, db: AsyncSession, user_id: str, session_id: str) -> bool:
        """Check if a session is in user's wishlist."""
        item = await self._wishlist_repo.get_by_user_and_session(db, user_id, session_id)
        return item is not None
