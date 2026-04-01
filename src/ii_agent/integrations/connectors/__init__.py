"""Connectors domain module."""

from .models import Connector, ConnectorType, ComposioProfile
from .types import ConnectorType, ComposioProfileStatus
from .base import BaseConnector, ConnectorData, ConnectorStatus
from .factory import ConnectorFactory
from .github import GitHubConnector
from .google_drive import GoogleDriveConnector
from .revenuecat import RevenueCatConnector
from .registry import ConnectorRegistry
from .repository import ConnectorRepository
from .exceptions import ConnectorNotFoundError, ConnectorConfigError, ConnectorStateError

# Create connector registry singleton
connector_registry = ConnectorRegistry()

# Register all connectors
connector_registry.register(ConnectorType.GOOGLE_DRIVE, GoogleDriveConnector)
connector_registry.register(ConnectorType.GITHUB, GitHubConnector)
connector_registry.register(ConnectorType.REVENUECAT, RevenueCatConnector)

__all__ = [
    # Models
    "Connector",
    "ConnectorType",
    "ComposioProfile",
    # Types (enums)
    "ConnectorType",
    "ComposioProfileStatus",
    # Repository
    "ConnectorRepository",
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
]
