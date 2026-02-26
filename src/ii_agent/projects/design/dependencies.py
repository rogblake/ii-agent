"""FastAPI dependencies for project design domain."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.core.llm.dependencies import (
    LLMBillingServiceDep,
    LLMExecutionServiceDep,
)
from ii_agent.engine.sandboxes.dependencies import SandboxServiceDep
from ii_agent.realtime.events.dependencies import EventServiceDep
from ii_agent.sessions.dependencies import SessionRepositoryDep
from ii_agent.settings.llm.dependencies import LLMSettingServiceDep
from ii_agent.projects.design.repository import ProjectDesignRepository
from ii_agent.projects.design.service import ProjectDesignService


def get_project_design_repository(
    session_repo: SessionRepositoryDep,
) -> ProjectDesignRepository:
    return ProjectDesignRepository(session_repo=session_repo)


ProjectDesignRepositoryDep = Annotated[ProjectDesignRepository, Depends(get_project_design_repository)]


def get_project_design_service(
    design_repo: ProjectDesignRepositoryDep,
    sandbox_service: SandboxServiceDep,
    event_service: EventServiceDep,
    llm_setting_service: LLMSettingServiceDep,
    llm_billing_service: LLMBillingServiceDep,
    llm_execution_service: LLMExecutionServiceDep,
) -> ProjectDesignService:
    return ProjectDesignService(
        repo=design_repo,
        sandbox_service=sandbox_service,
        event_service=event_service,
        llm_setting_service=llm_setting_service,
        llm_billing_service=llm_billing_service,
        llm_execution_service=llm_execution_service,
        config=get_settings(),
    )


ProjectDesignServiceDep = Annotated[ProjectDesignService, Depends(get_project_design_service)]
