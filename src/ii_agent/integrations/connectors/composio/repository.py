"""Repository layer for Composio profiles - stateless data access only."""

import uuid
from typing import Optional, List

from sqlalchemy import select, delete, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.base import BaseRepository
from ii_agent.integrations.connectors.models import ComposioProfile


class ComposioProfileRepository(BaseRepository[ComposioProfile]):
    """Stateless data access layer for ComposioProfile model.

    Inherits from BaseRepository: get_by_id, save, update.
    Every method receives ``db: AsyncSession`` as its first argument
    so that the caller controls transaction boundaries.
    """

    model = ComposioProfile

    # ---- Read ----

    async def get_by_id_and_user(
        self, db: AsyncSession, profile_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[ComposioProfile]:
        result = await db.execute(
            select(ComposioProfile).where(
                ComposioProfile.id == profile_id,
                ComposioProfile.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_profiles_by_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        toolkit_slug: Optional[str] = None,
    ) -> List[ComposioProfile]:
        stmt = select(ComposioProfile).where(ComposioProfile.user_id == user_id)
        if toolkit_slug:
            stmt = stmt.where(ComposioProfile.toolkit_slug == toolkit_slug)
        stmt = stmt.order_by(ComposioProfile.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_enabled_profiles_by_user(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> List[ComposioProfile]:
        result = await db.execute(
            select(ComposioProfile).where(
                ComposioProfile.user_id == user_id,
                ComposioProfile.status == "enable",
            )
        )
        return list(result.scalars().all())

    async def get_user_mcp_server_id(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> Optional[str]:
        result = await db.execute(
            select(ComposioProfile.mcp_server_id)
            .where(ComposioProfile.user_id == user_id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_profiles_by_mcp_server(
        self, db: AsyncSession, user_id: uuid.UUID, mcp_server_id: str
    ) -> List[ComposioProfile]:
        result = await db.execute(
            select(ComposioProfile).where(
                ComposioProfile.user_id == user_id,
                ComposioProfile.mcp_server_id == mcp_server_id,
            )
        )
        return list(result.scalars().all())

    async def count_profiles_with_name_prefix(
        self, db: AsyncSession, user_id: uuid.UUID, base_name: str
    ) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(ComposioProfile)
            .where(
                ComposioProfile.user_id == user_id,
                ComposioProfile.profile_name.like(f"{base_name}%"),
            )
        )
        return result.scalar() or 0

    async def profile_name_exists(
        self, db: AsyncSession, user_id: uuid.UUID, profile_name: str
    ) -> bool:
        result = await db.execute(
            select(ComposioProfile.id)
            .where(
                ComposioProfile.user_id == user_id,
                ComposioProfile.profile_name == profile_name,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def find_pending_profile(
        self, db: AsyncSession, user_id: uuid.UUID, toolkit_slug: str
    ) -> Optional[ComposioProfile]:
        result = await db.execute(
            select(ComposioProfile).where(
                ComposioProfile.user_id == user_id,
                ComposioProfile.toolkit_slug == toolkit_slug,
                ComposioProfile.status == "pending",
            )
        )
        return result.scalar_one_or_none()

    async def find_profile_by_connected_account(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        toolkit_slug: str,
        connected_account_id: str,
    ) -> Optional[ComposioProfile]:
        result = await db.execute(
            select(ComposioProfile)
            .where(
                ComposioProfile.user_id == user_id,
                ComposioProfile.toolkit_slug == toolkit_slug,
                ComposioProfile.connected_account_id == connected_account_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def check_existing_auth_config(
        self, db: AsyncSession, toolkit_slug: str
    ) -> Optional[str]:
        """Return the first auth_config_id for a given toolkit_slug, or None."""
        result = await db.execute(
            select(ComposioProfile.auth_config_id)
            .where(ComposioProfile.toolkit_slug == toolkit_slug)
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ---- Write ----

    async def update_status(
        self, db: AsyncSession, profile_id: uuid.UUID, user_id: uuid.UUID, status: str
    ) -> bool:
        result = await db.execute(
            update(ComposioProfile)
            .where(
                ComposioProfile.id == profile_id,
                ComposioProfile.user_id == user_id,
            )
            .values(status=status)
        )
        return result.rowcount > 0

    async def update_enabled_tools(
        self, db: AsyncSession, profile_id: uuid.UUID, enabled_tools: list
    ) -> bool:
        result = await db.execute(
            update(ComposioProfile)
            .where(ComposioProfile.id == profile_id)
            .values(enabled_tools=enabled_tools)
        )
        return result.rowcount > 0

    async def delete(self, db: AsyncSession, profile_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        result = await db.execute(
            delete(ComposioProfile).where(
                ComposioProfile.id == profile_id,
                ComposioProfile.user_id == user_id,
            )
        )
        return result.rowcount > 0

    async def delete_by_id(self, db: AsyncSession, profile_id: uuid.UUID) -> bool:
        result = await db.execute(
            delete(ComposioProfile).where(ComposioProfile.id == profile_id)
        )
        return result.rowcount > 0
