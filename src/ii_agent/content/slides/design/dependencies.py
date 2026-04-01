"""FastAPI dependencies for slide design domain."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep
from ii_agent.content.slides.dependencies import SlideRepositoryDep
from ii_agent.sessions.dependencies import SessionRepositoryDep
from ii_agent.content.slides.design.repository import SlideDesignRepository
from ii_agent.content.slides.design.service import SlideDesignService


def get_slide_design_repository(
    session_repo: SessionRepositoryDep,
    slide_repo: SlideRepositoryDep,
) -> SlideDesignRepository:
    return SlideDesignRepository(session_repo=session_repo, slide_repo=slide_repo)


SlideDesignRepositoryDep = Annotated[SlideDesignRepository, Depends(get_slide_design_repository)]


def _get_slide_design_service(container: ContainerDep) -> SlideDesignService:
    return container.slide_design_service


SlideDesignServiceDep = Annotated[SlideDesignService, Depends(_get_slide_design_service)]
