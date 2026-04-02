"""Base connector abstract class for external service integrations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.integrations.connectors.models import Connector, ConnectorTypeEnum


@dataclass
class ConnectorData:
    """Data returned from OAuth callback."""

    access_token: str
    refresh_token: Optional[str] = None
    token_expiry: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ConnectorStatus:
    """Connector connection status."""

    is_connected: bool
    connector_type: str
    metadata: Optional[Dict[str, Any]] = None
    access_token: Optional[str] = None


class BaseConnector(ABC):
    """Abstract base class for all external service connectors.

    All connector implementations must extend this class and implement
    the required abstract methods. This ensures a consistent interface
    for OAuth flows, token management, and connection handling.
    """

    def __init__(self, db_session: AsyncSession):
        """Initialize connector with database session.

        Args:
            db_session: SQLAlchemy async session for database operations
        """
        self.db_session = db_session

    @property
    @abstractmethod
    def connector_type(self) -> ConnectorTypeEnum:
        """Return the connector type enum value.

        Returns:
            ConnectorTypeEnum: The type of this connector
        """
        pass

    @property
    @abstractmethod
    def scopes(self) -> list[str]:
        """Return the OAuth scopes required by this connector.

        Returns:
            list[str]: List of OAuth scope strings
        """
        pass

    @abstractmethod
    async def get_auth_url(self, state: str) -> str:
        """Generate OAuth authorization URL.

        Args:
            state: Encrypted state parameter for CSRF protection

        Returns:
            str: OAuth authorization URL to redirect user to
        """
        pass

    @abstractmethod
    async def handle_callback(self, code: str, state: str) -> ConnectorData:
        """Handle OAuth callback and exchange code for tokens.

        Args:
            code: Authorization code from OAuth provider
            state: State parameter for validation

        Returns:
            ConnectorData: Access token, refresh token, expiry, and metadata

        Raises:
            HTTPException: If OAuth exchange fails
        """
        pass

    @abstractmethod
    async def refresh_access_token(self, connector: Connector) -> ConnectorData:
        """Refresh the access token using refresh token.

        Args:
            connector: Database connector model with existing tokens

        Returns:
            ConnectorData: New access token and expiry information

        Raises:
            HTTPException: If token refresh fails
        """
        pass

    @abstractmethod
    async def validate_token(self, access_token: str) -> bool:
        """Validate if the access token is still valid.

        Args:
            access_token: The access token to validate

        Returns:
            bool: True if token is valid, False otherwise
        """
        pass

    @abstractmethod
    async def revoke_access(self, connector: Connector) -> bool:
        """Revoke access tokens with the OAuth provider.

        Args:
            connector: Database connector model with tokens to revoke

        Returns:
            bool: True if revocation successful, False otherwise
        """
        pass

    async def connect(
        self,
        user_id: str,
        connector_data: ConnectorData,
    ) -> Connector:
        """Store connector credentials in database.

        This method handles the database operations for storing connector
        credentials after successful OAuth flow. It can be overridden by
        subclasses if custom logic is needed.

        Args:
            user_id: User ID to associate with connector
            connector_data: Token and metadata from OAuth flow

        Returns:
            Connector: Database model of the created/updated connector
        """
        from sqlalchemy import select

        stmt = select(Connector).where(
            Connector.user_id == user_id,
            Connector.connector_type == self.connector_type.value,
        )
        result = await self.db_session.execute(stmt)
        existing_connector = result.scalar_one_or_none()

        if existing_connector:
            existing_connector.access_token = connector_data.access_token
            existing_connector.refresh_token = connector_data.refresh_token
            existing_connector.token_expiry = connector_data.token_expiry
            existing_connector.connector_metadata = connector_data.metadata
            existing_connector.updated_at = datetime.utcnow()
            await self.db_session.commit()
            await self.db_session.refresh(existing_connector)
            return existing_connector
        else:
            new_connector = Connector(
                user_id=user_id,
                connector_type=self.connector_type.value,
                access_token=connector_data.access_token,
                refresh_token=connector_data.refresh_token,
                token_expiry=connector_data.token_expiry,
                connector_metadata=connector_data.metadata,
            )
            self.db_session.add(new_connector)
            await self.db_session.commit()
            await self.db_session.refresh(new_connector)
            return new_connector

    async def disconnect(self, user_id: str) -> bool:
        """Disconnect and remove connector from database.

        Args:
            user_id: User ID to disconnect connector for

        Returns:
            bool: True if disconnection successful
        """
        from sqlalchemy import delete, select

        stmt = select(Connector).where(
            Connector.user_id == user_id,
            Connector.connector_type == self.connector_type.value,
        )
        result = await self.db_session.execute(stmt)
        connector = result.scalar_one_or_none()

        if connector:
            await self.revoke_access(connector)

            delete_stmt = delete(Connector).where(
                Connector.user_id == user_id,
                Connector.connector_type == self.connector_type.value,
            )
            await self.db_session.execute(delete_stmt)
            await self.db_session.commit()

        return True

    async def get_status(self, user_id: str) -> ConnectorStatus:
        """Get connector connection status for user.

        Args:
            user_id: User ID to check status for

        Returns:
            ConnectorStatus: Connection status and metadata
        """
        from sqlalchemy import select

        stmt = select(Connector).where(
            Connector.user_id == user_id,
            Connector.connector_type == self.connector_type.value,
        )
        result = await self.db_session.execute(stmt)
        connector = result.scalar_one_or_none()

        if not connector:
            return ConnectorStatus(
                is_connected=False,
                connector_type=self.connector_type.value,
            )

        return ConnectorStatus(
            is_connected=True,
            connector_type=self.connector_type.value,
            metadata=connector.connector_metadata,
            access_token=connector.access_token,
        )

    async def get_connector(self, user_id: str) -> Optional[Connector]:
        """Retrieve connector from database.

        Args:
            user_id: User ID to get connector for

        Returns:
            Optional[Connector]: Connector model or None if not found
        """
        from sqlalchemy import select

        stmt = select(Connector).where(
            Connector.user_id == user_id,
            Connector.connector_type == self.connector_type.value,
        )
        result = await self.db_session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_valid_token(self, user_id: str) -> Optional[str]:
        """Get a valid access token, refreshing if necessary.

        This is a convenience method that handles token refresh automatically.

        Args:
            user_id: User ID to get token for

        Returns:
            Optional[str]: Valid access token or None if not connected
        """
        connector = await self.get_connector(user_id)
        if not connector:
            return None

        if await self._should_refresh_token(connector):
            connector_data = await self.refresh_access_token(connector)
            connector.access_token = connector_data.access_token
            connector.refresh_token = connector_data.refresh_token or connector.refresh_token
            connector.token_expiry = connector_data.token_expiry
            connector.updated_at = datetime.utcnow()
            await self.db_session.commit()
            await self.db_session.refresh(connector)

        return connector.access_token

    async def _should_refresh_token(self, connector: Connector) -> bool:
        """Check if token should be refreshed.

        Args:
            connector: Connector model to check

        Returns:
            bool: True if token should be refreshed
        """
        if not connector.token_expiry or not connector.refresh_token:
            return False

        from datetime import timezone

        now = datetime.now(timezone.utc)
        expiry = connector.token_expiry

        if expiry.tzinfo is None:
            from datetime import timezone
            expiry = expiry.replace(tzinfo=timezone.utc)

        from datetime import timedelta
        return expiry <= now + timedelta(minutes=5)
