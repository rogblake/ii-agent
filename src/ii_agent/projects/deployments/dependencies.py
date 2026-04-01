"""FastAPI dependencies for deployments domain.

Thin accessors that pull services from :class:`ApplicationContainer`.
"""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep
from ii_agent.projects.deployments.repository import DeploymentsRepository
from ii_agent.projects.deployments.service import DeploymentsService


# ==================== Repository Dependencies ====================


def get_deployments_repository() -> DeploymentsRepository:
    """Provide DeploymentsRepository instance."""
    return DeploymentsRepository()


DeploymentsRepositoryDep = Annotated[DeploymentsRepository, Depends(get_deployments_repository)]


# ==================== Service Dependencies (container-backed) =============


def _get_deployments_service(container: ContainerDep) -> DeploymentsService:
    return container.deployments_service


DeploymentsServiceDep = Annotated[DeploymentsService, Depends(_get_deployments_service)]


__all__ = [
    "get_deployments_repository",
    "DeploymentsRepositoryDep",
    "DeploymentsServiceDep",
]
