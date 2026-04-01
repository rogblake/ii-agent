"""Repository layer for waitlist - data access only."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.users.models import WaitlistEntry


class WaitlistRepository:
    """Data access layer for WaitlistEntry model."""

    async def get_by_email(self, db: AsyncSession, email: str) -> WaitlistEntry | None:
        """Get a waitlist entry by email (case-insensitive)."""
        result = await db.execute(
            select(WaitlistEntry).where(func.lower(WaitlistEntry.email) == email.lower())
        )
        return result.scalar_one_or_none()
