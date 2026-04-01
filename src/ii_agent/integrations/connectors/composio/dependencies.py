"""FastAPI dependencies for Composio composio domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep
from ii_agent.integrations.connectors.composio.repository import ComposioProfileRepository
from ii_agent.integrations.connectors.composio.service import ComposioService


# ==================== Repository Dependencies ====================


def get_composio_profile_repository() -> ComposioProfileRepository:
    """Provide ComposioProfileRepository instance."""
    return ComposioProfileRepository()


ComposioProfileRepositoryDep = Annotated[ComposioProfileRepository, Depends(get_composio_profile_repository)]


# ==================== Service Dependencies ====================


def _get_composio_service(container: ContainerDep) -> ComposioService:
    return container.composio_service


ComposioServiceDep = Annotated[ComposioService, Depends(_get_composio_service)]
