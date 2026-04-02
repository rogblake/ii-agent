"""LLM config resolution — replaces scattered is_user_provided_model checks."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from ii_agent.core.config.llm_config import LLMConfig
    from ii_agent.core.config.settings import Settings
    from ii_agent.settings.llm.service import LLMSettingService

logger = logging.getLogger(__name__)


class LLMConfigResolver:
    """Resolve LLM configuration for a user/session."""

    def __init__(
        self,
        *,
        llm_setting_service: LLMSettingService,
        config: Settings,
    ) -> None:
        self._llm_setting_service = llm_setting_service
        self._config = config

    async def resolve(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        model_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> LLMConfig:
        """Resolve the LLM configuration for a request."""
        return await self._llm_setting_service.get_llm_settings(
            db,
            session=None,
            source=None,
            model_id=model_id,
        )

    @staticmethod
    def is_user_provided_model(llm_config: LLMConfig) -> bool:
        """Check whether the resolved config points to a user-owned key."""
        return llm_config.is_user_model()
