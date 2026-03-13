"""Connectors domain module.

Import pattern:
    from ii_agent.integrations.connectors import (
        Connector,
        ConnectorTypeEnum,
        ConnectorService,
        router,
    )
"""

from .models import Connector, ConnectorTypeEnum, ComposioProfile
from .base import BaseConnector, ConnectorData, ConnectorStatus
from .factory import ConnectorFactory
from .github import GitHubConnector
from .google_drive import GoogleDriveConnector
from .revenuecat import RevenueCatConnector
from .registry import ConnectorRegistry
from .service import ConnectorService
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
    # Service
    "ConnectorService",
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
    "connector_registry",
    # Router
    "router",
]
