"""FastAPI dependencies for design domain."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from ii_agent.content.slides.dependencies import SlideRepositoryDep
from ii_agent.core.config.settings import get_settings
from ii_agent.design.repository import DesignRepository
from ii_agent.design.service import DesignService
from ii_agent.engine.sandboxes.dependencies import SandboxServiceDep
from ii_agent.realtime.events.dependencies import EventServiceDep
from ii_agent.sessions.dependencies import SessionRepositoryDep
from ii_agent.settings.llm.dependencies import LLMSettingServiceDep


def get_design_repository(
    session_repo: SessionRepositoryDep,
    slide_repo: SlideRepositoryDep,
) -> DesignRepository:
    """Provide DesignRepository instance."""
    return DesignRepository(session_repo=session_repo, slide_repo=slide_repo)


DesignRepositoryDep = Annotated[DesignRepository, Depends(get_design_repository)]


def get_design_service(
    design_repo: DesignRepositoryDep,
    sandbox_service: SandboxServiceDep,
    event_service: EventServiceDep,
    llm_setting_service: LLMSettingServiceDep,
) -> DesignService:
    """Provide DesignService instance with explicit dependency injection."""
    return DesignService(
        repo=design_repo,
        sandbox_service=sandbox_service,
        event_service=event_service,
        llm_setting_service=llm_setting_service,
        config=get_settings(),
    )


DesignServiceDep = Annotated[DesignService, Depends(get_design_service)]


__all__ = [
    "get_design_repository",
    "get_design_service",
    "DesignRepositoryDep",
    "DesignServiceDep",
]
