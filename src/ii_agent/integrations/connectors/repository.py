"""Repository layer for connectors domain - data access only."""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.repository import BaseRepository
from ii_agent.integrations.connectors.models import Connector


class ConnectorRepository(BaseRepository[Connector]):
    """Data access layer for Connector model."""

    model = Connector

    async def get_by_user(self, db: AsyncSession, user_id: str) -> List[Connector]:
        """Get all connectors for a user."""
        result = await db.execute(
            select(Connector).where(Connector.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_by_user_and_type(
        self, db: AsyncSession, user_id: str, connector_type: str
    ) -> Optional[Connector]:
        """Get a connector by user ID and type."""
        result = await db.execute(
            select(Connector).where(
                Connector.user_id == user_id,
                Connector.connector_type == connector_type,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_token_and_type(
        self, db: AsyncSession, token: str, connector_type: str
    ) -> Optional[Connector]:
        """Get a connector by access token and type."""
        result = await db.execute(
            select(Connector).where(
                Connector.access_token == token,
                Connector.connector_type == connector_type,
            )
        )
        return result.scalar_one_or_none()
