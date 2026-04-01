"""Repository layer for wishlist - data access only."""

import uuid
from typing import List, Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ii_agent.core.db.repository import BaseRepository
from ii_agent.sessions.wishlist.models import SessionWishlist


class WishlistRepository(BaseRepository[SessionWishlist]):
    """Data access layer for SessionWishlist model."""

    model = SessionWishlist

    async def get_user_wishlists(self, db: AsyncSession, user_id: uuid.UUID) -> List[SessionWishlist]:
        """Get all wishlist items for a user with session eager-loaded."""
        result = await db.execute(
            select(SessionWishlist)
            .options(selectinload(SessionWishlist.session))
            .where(SessionWishlist.user_id == user_id)
            .order_by(SessionWishlist.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_user_and_session(
        self, db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
    ) -> Optional[SessionWishlist]:
        """Get a wishlist item by user and session."""
        result = await db.execute(
            select(SessionWishlist).where(
                and_(
                    SessionWishlist.user_id == user_id,
                    SessionWishlist.session_id == session_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def create(self, db: AsyncSession, wishlist_item: SessionWishlist) -> SessionWishlist:
        """Persist a new wishlist item (no refresh needed)."""
        db.add(wishlist_item)
        await db.flush()
        return wishlist_item

    async def delete_by_user_and_session(
        self, db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
    ) -> bool:
        """Delete a wishlist item by user and session. Returns True if deleted."""
        result = await db.execute(
            delete(SessionWishlist).where(
                and_(
                    SessionWishlist.user_id == user_id,
                    SessionWishlist.session_id == session_id,
                )
            )
        )
        return result.rowcount > 0
