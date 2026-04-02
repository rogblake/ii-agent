"""Repository layer for llm_settings domain - data access only."""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.repository import BaseRepository
from ii_agent.settings.llm.models import LLMSetting


class LLMSettingRepository(BaseRepository[LLMSetting]):
    """Data access layer for LLMSetting model."""

    model = LLMSetting

    async def get_by_id_and_user(
        self, db: AsyncSession, setting_id: str, user_id: str
    ) -> Optional[LLMSetting]:
        """Get an LLM setting by ID for a specific user."""
        result = await db.execute(
            select(LLMSetting).where(
                LLMSetting.id == setting_id,
                LLMSetting.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_model_and_user(
        self, db: AsyncSession, model_name: str, user_id: str
    ) -> Optional[LLMSetting]:
        """Get an LLM setting by model name for a specific user."""
        result = await db.execute(
            select(LLMSetting).where(
                LLMSetting.model == model_name,
                LLMSetting.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self, db: AsyncSession, user_id: str, *, api_type: Optional[str] = None
    ) -> List[LLMSetting]:
        """List all LLM settings for a user, optionally filtered by API type."""
        query = select(LLMSetting).where(LLMSetting.user_id == user_id)

        if api_type:
            query = query.where(LLMSetting.api_type == api_type)

        query = query.order_by(LLMSetting.created_at)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def delete(self, db: AsyncSession, setting: LLMSetting) -> None:
        """Delete an LLM setting."""
        await db.delete(setting)
        await db.flush()
