"""Connector registry for auto-discovery and registration."""

from typing import Dict, Type

from ii_agent.integrations.connectors.models import ConnectorType
from .base import BaseConnector


class ConnectorRegistry:
    """Registry for managing connector implementations.

    This registry allows for easy extensibility - new connectors can be
    registered at runtime, making it simple to add new integrations.
    """

    _connectors: Dict[ConnectorType, Type[BaseConnector]] = {}

    @classmethod
    def register(cls, connector_type: ConnectorType, connector_class: Type[BaseConnector]):
        """Register a connector implementation.

        Args:
            connector_type: The connector type enum
            connector_class: The connector class to register

        Example:
            ConnectorRegistry.register(
                ConnectorType.GOOGLE_DRIVE,
                GoogleDriveConnector
            )
        """
        cls._connectors[connector_type] = connector_class

    @classmethod
    def get(cls, connector_type: ConnectorType) -> Type[BaseConnector]:
        """Get a connector class by type.

        Args:
            connector_type: The connector type to retrieve

        Returns:
            Type[BaseConnector]: The registered connector class

        Raises:
            ValueError: If connector type is not registered
        """
        if connector_type not in cls._connectors:
            raise ValueError(f"Connector type {connector_type} is not registered")
        return cls._connectors[connector_type]

    @classmethod
    def get_all(cls) -> Dict[ConnectorType, Type[BaseConnector]]:
        """Get all registered connectors.

        Returns:
            Dict[ConnectorType, Type[BaseConnector]]: All registered connectors
        """
        return cls._connectors.copy()

    @classmethod
    def is_registered(cls, connector_type: ConnectorType) -> bool:
        """Check if a connector type is registered.

        Args:
            connector_type: The connector type to check

        Returns:
            bool: True if registered, False otherwise
        """
        return connector_type in cls._connectors
