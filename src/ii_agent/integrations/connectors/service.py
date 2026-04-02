"""Connector service for managing connector records and tokens."""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.integrations.connectors.models import Connector, ConnectorTypeEnum
from ii_agent.integrations.connectors.repository import ConnectorRepository

logger = logging.getLogger(__name__)


class ConnectorService:
    """Service for connector database operations."""

    def __init__(self, *, connector_repo: ConnectorRepository, config: Settings) -> None:
        self._repo = connector_repo
        self._config = config

    async def save_mcp_token(
        self,
        db: AsyncSession,
        *,
        access_token: str,
        user_id: str,
        user_email: str,
        expires_in: int = 3600,
    ) -> None:
        """Save an MCP OAuth token for a user."""
        # Calculate expiry time
        token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Check if user already has an MCP connector
        connector = await self._repo.get_by_user_and_type(
            db, user_id, ConnectorTypeEnum.CHATGPT_MCP.value
        )

        if connector:
            # Update existing connector
            connector.access_token = access_token
            connector.token_expiry = token_expiry
            connector.connector_metadata = {
                "user_email": user_email,
            }
        else:
            # Create new connector
            connector = Connector(
                id=str(uuid.uuid4()),
                user_id=user_id,
                connector_type=ConnectorTypeEnum.CHATGPT_MCP.value,
                access_token=access_token,
                token_expiry=token_expiry,
                connector_metadata={
                    "user_email": user_email,
                },
            )
            db.add(connector)

        await db.flush()

    async def get_user_by_mcp_token(
        self,
        db: AsyncSession,
        *,
        token: str,
    ) -> Optional[Dict[str, str]]:
        """Get user info by MCP token."""
        connector = await self._repo.get_by_token_and_type(
            db, token, ConnectorTypeEnum.CHATGPT_MCP.value
        )

        if not connector:
            return None

        # Check if token is expired
        if connector.token_expiry and connector.token_expiry < datetime.now(timezone.utc):
            logger.warning("MCP token expired for user %s", connector.user_id)
            return None

        metadata = connector.connector_metadata or {}
        return {
            "user_id": connector.user_id,
            "user_email": metadata.get("user_email", ""),
        }
