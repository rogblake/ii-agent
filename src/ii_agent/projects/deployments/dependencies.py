from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.projects.dependencies import ProjectRepositoryDep
from ii_agent.projects.deployments.repository import DeploymentsRepository
from ii_agent.projects.deployments.service import DeploymentsService


def get_deployments_repository() -> DeploymentsRepository:
    """Provide DeploymentsRepository instance."""
    return DeploymentsRepository()


DeploymentsRepositoryDep = Annotated[DeploymentsRepository, Depends(get_deployments_repository)]


def get_deployments_service(
    project_repo: ProjectRepositoryDep,
    deployments_repo: DeploymentsRepositoryDep,
) -> DeploymentsService:
    """Provide DeploymentsService instance with explicit repo injection."""
    return DeploymentsService(
        project_repo=project_repo,
        deployments_repo=deployments_repo,
        config=get_settings(),
    )


DeploymentsServiceDep = Annotated[DeploymentsService, Depends(get_deployments_service)]
