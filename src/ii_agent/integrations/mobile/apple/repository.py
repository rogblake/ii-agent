"""Repository for Apple credentials."""

from __future__ import annotations

import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.repository import BaseRepository
from ii_agent.integrations.mobile.apple.models import AppleCredential


class AppleCredentialRepository(BaseRepository[AppleCredential]):
    """Data access helpers for Apple credentials."""

    model = AppleCredential

    async def get_by_user_and_apple_id(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        apple_id: str,
    ) -> AppleCredential | None:
        result = await db.execute(
            select(AppleCredential).where(
                AppleCredential.user_id == user_id,
                AppleCredential.apple_id == apple_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_by_user(self, db: AsyncSession, user_id: uuid.UUID) -> AppleCredential | None:
        result = await db.execute(
            select(AppleCredential)
            .where(AppleCredential.user_id == user_id)
            .order_by(
                (AppleCredential.apple_id == "pending").asc(),
                desc(AppleCredential.updated_at),
            )
        )
        return result.scalars().first()

    async def get_latest_authenticated_by_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> AppleCredential | None:
        result = await db.execute(
            select(AppleCredential)
            .where(
                AppleCredential.user_id == user_id,
                AppleCredential.auth_state == "authenticated",
            )
            .order_by(desc(AppleCredential.updated_at))
        )
        return result.scalars().first()
