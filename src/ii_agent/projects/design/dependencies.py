"""FastAPI dependencies for project design domain.

Thin accessors that pull services from :class:`ApplicationContainer`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep
from ii_agent.projects.design.repository import ProjectDesignRepository
from ii_agent.projects.design.service import ProjectDesignService
from ii_agent.sessions.dependencies import SessionRepositoryDep


# ==================== Repository Dependencies ====================


def get_project_design_repository(
    session_repo: SessionRepositoryDep,
) -> ProjectDesignRepository:
    """Provide ProjectDesignRepository (composes SessionRepository)."""
    return ProjectDesignRepository(session_repo=session_repo)


ProjectDesignRepositoryDep = Annotated[
    ProjectDesignRepository, Depends(get_project_design_repository)
]


# ==================== Service Dependencies (container-backed) =============


def _get_project_design_service(container: ContainerDep) -> ProjectDesignService:
    return container.project_design_service


ProjectDesignServiceDep = Annotated[ProjectDesignService, Depends(_get_project_design_service)]


__all__ = [
    "get_project_design_repository",
    "ProjectDesignRepositoryDep",
    "ProjectDesignServiceDep",
]
