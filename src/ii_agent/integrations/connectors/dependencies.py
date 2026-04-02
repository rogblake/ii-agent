"""FastAPI dependencies for connectors domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.integrations.connectors.repository import ConnectorRepository
from ii_agent.integrations.connectors.service import ConnectorService


def get_connector_repository() -> ConnectorRepository:
    """Provide ConnectorRepository instance."""
    return ConnectorRepository()


ConnectorRepositoryDep = Annotated[ConnectorRepository, Depends(get_connector_repository)]


def get_connector_service(
    connector_repo: ConnectorRepositoryDep,
) -> ConnectorService:
    """Provide ConnectorService instance with explicit config."""
    return ConnectorService(
        connector_repo=connector_repo,
        config=get_settings(),
    )


ConnectorServiceDep = Annotated[ConnectorService, Depends(get_connector_service)]


__all__ = [
    "get_connector_repository",
    "get_connector_service",
    "ConnectorRepositoryDep",
    "ConnectorServiceDep",
]
