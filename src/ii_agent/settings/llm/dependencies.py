"""FastAPI dependencies for llm_settings domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.sessions.dependencies import SessionRepositoryDep
from ii_agent.settings.llm.repository import LLMSettingRepository
from ii_agent.settings.llm.service import LLMSettingService


# ==================== Repository Dependencies ====================


def get_llm_setting_repository() -> LLMSettingRepository:
    """Provide LLMSettingRepository instance."""
    return LLMSettingRepository()


LLMSettingRepositoryDep = Annotated[LLMSettingRepository, Depends(get_llm_setting_repository)]


# ==================== Service Dependencies ====================


def get_llm_setting_service(
    repo: LLMSettingRepositoryDep,
    session_repo: SessionRepositoryDep,
) -> LLMSettingService:
    """Provide LLMSettingService instance with explicit repo injection."""
    return LLMSettingService(
        repo=repo,
        session_repo=session_repo,
        config=get_settings(),
    )


LLMSettingServiceDep = Annotated[LLMSettingService, Depends(get_llm_setting_service)]


__all__ = [
    "get_llm_setting_repository",
    "get_llm_setting_service",
    "LLMSettingRepositoryDep",
    "LLMSettingServiceDep",
]
