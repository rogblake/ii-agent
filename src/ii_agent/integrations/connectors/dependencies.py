"""FastAPI dependencies for connectors domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep
from ii_agent.integrations.connectors.repository import ConnectorRepository
from ii_agent.integrations.connectors.service import ConnectorService


# ==================== Repository Dependencies ====================


def get_connector_repository() -> ConnectorRepository:
    """Provide ConnectorRepository instance."""
    return ConnectorRepository()


ConnectorRepositoryDep = Annotated[ConnectorRepository, Depends(get_connector_repository)]


# ==================== Service Dependencies ====================


def _get_connector_service(container: ContainerDep) -> ConnectorService:
    return container.connector_service


ConnectorServiceDep = Annotated[ConnectorService, Depends(_get_connector_service)]
