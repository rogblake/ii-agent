"""Repository layer for usage domain - data access only."""

from decimal import Decimal
from typing import Optional, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.usage.models import SessionMetrics


class MetricsRepository:
    """Data access layer for SessionMetrics model."""

    async def get_by_session_id(self, db: AsyncSession, session_id: str) -> Optional[SessionMetrics]:
        """Get metrics record for a session."""
        result = await db.execute(
            select(SessionMetrics).where(SessionMetrics.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self, db: AsyncSession, session_id: str, credits: Union[Decimal, float]
    ) -> SessionMetrics:
        """Create a new session metrics record."""
        metrics = SessionMetrics(
            session_id=session_id,
            credits=Decimal(str(credits)),
        )
        db.add(metrics)
        await db.flush()
        await db.refresh(metrics)
        return metrics
