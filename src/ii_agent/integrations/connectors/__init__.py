"""Connectors domain module.

Import pattern:
    from ii_agent.integrations.connectors import (
        Connector,
        ConnectorType,
        ConnectorService,
        ConnectorServiceDep,
        router,
    )
"""

from .models import Connector, ConnectorTypeEnum, ComposioProfile
from .types import ConnectorType, ComposioProfileStatus
from .base import BaseConnector, ConnectorData, ConnectorStatus
from .factory import ConnectorFactory
from .github import GitHubConnector
from .google_drive import GoogleDriveConnector
from .revenuecat import RevenueCatConnector
from .registry import ConnectorRegistry
from .repository import ConnectorRepository
from .service import ConnectorService
from .dependencies import ConnectorRepositoryDep, ConnectorServiceDep
from .exceptions import ConnectorNotFoundError, ConnectorConfigError, ConnectorStateError
from .router import router

# Create connector registry singleton
connector_registry = ConnectorRegistry()

# Register all connectors
connector_registry.register(ConnectorTypeEnum.GOOGLE_DRIVE, GoogleDriveConnector)
connector_registry.register(ConnectorTypeEnum.GITHUB, GitHubConnector)
connector_registry.register(ConnectorTypeEnum.REVENUECAT, RevenueCatConnector)

__all__ = [
    # Models
    "Connector",
    "ConnectorTypeEnum",
    "ComposioProfile",
    # Types (enums)
    "ConnectorType",
    "ComposioProfileStatus",
    # Repository
    "ConnectorRepository",
    # Service
    "ConnectorService",
    # Dependencies (Dep aliases)
    "ConnectorRepositoryDep",
    "ConnectorServiceDep",
    # Exceptions
    "ConnectorNotFoundError",
    "ConnectorConfigError",
    "ConnectorStateError",
    # Base classes
    "BaseConnector",
    "ConnectorData",
    "ConnectorStatus",
    # Implementations
    "GitHubConnector",
    "GoogleDriveConnector",
    "RevenueCatConnector",
    # Factory and registry
    "ConnectorFactory",
    "ConnectorRegistry",
    "connector_registry",
    # Router
    "router",
]
