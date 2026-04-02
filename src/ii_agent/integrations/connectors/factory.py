"""Factory for creating connector instances."""

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.integrations.connectors.models import ConnectorTypeEnum
from .base import BaseConnector
from .registry import ConnectorRegistry


class ConnectorFactory:
    """Factory for creating connector instances based on type.

    This factory uses the ConnectorRegistry to instantiate the correct
    connector implementation based on the connector type.
    """

    @staticmethod
    def create(
        connector_type: ConnectorTypeEnum,
        db_session: AsyncSession,
    ) -> BaseConnector:
        """Create a connector instance.

        Args:
            connector_type: Type of connector to create
            db_session: Database session for connector operations

        Returns:
            BaseConnector: Instantiated connector service

        Raises:
            ValueError: If connector type is not registered

        Example:
            connector = ConnectorFactory.create(
                ConnectorTypeEnum.GOOGLE_DRIVE,
                db_session
            )
            auth_url = await connector.get_auth_url(state)
        """
        connector_class = ConnectorRegistry.get(connector_type)
        return connector_class(db_session)

    @staticmethod
    def create_by_name(
        connector_type_name: str,
        db_session: AsyncSession,
    ) -> BaseConnector:
        """Create a connector instance by type name string.

        Args:
            connector_type_name: String name of connector type (e.g., 'google_drive')
            db_session: Database session for connector operations

        Returns:
            BaseConnector: Instantiated connector service

        Raises:
            ValueError: If connector type name is invalid or not registered

        Example:
            connector = ConnectorFactory.create_by_name(
                'github',
                db_session
            )
        """
        try:
            connector_type = ConnectorTypeEnum(connector_type_name)
        except ValueError:
            raise ValueError(f"Invalid connector type: {connector_type_name}")

        return ConnectorFactory.create(connector_type, db_session)
