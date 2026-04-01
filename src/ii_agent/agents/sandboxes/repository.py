"""Sandbox data access layer."""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.agents.sandboxes.models import AgentSandbox
from ii_agent.agents.sandboxes.types import SandboxStatus
from ii_agent.core.db.base import BaseRepository


class SandboxRepository(BaseRepository[AgentSandbox]):
    model = AgentSandbox

    async def get_active_by_session_id(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
    ) -> Optional[AgentSandbox]:
        """Find the active (non-deleted) sandbox for a session."""
        result = await db.execute(
            select(AgentSandbox)
            .where(
                AgentSandbox.session_id == session_id,
                AgentSandbox.status != SandboxStatus.DELETED,
            )
            .order_by(AgentSandbox.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # Alias for consumers that use the shorter name
    get_by_session_id = get_active_by_session_id

    async def update_status(
        self,
        db: AsyncSession,
        sandbox_id: uuid.UUID,
        status: SandboxStatus,
    ) -> Optional[AgentSandbox]:
        """Update the sandbox status."""
        record = await self.get_by_id(db, sandbox_id)
        if record is None:
            return None
        record.status = status
        await db.flush()
        await db.refresh(record)
        return record

    async def update_provider_info(
        self,
        db: AsyncSession,
        sandbox_id: uuid.UUID,
        *,
        status: Optional[SandboxStatus] = None,
        provider_sandbox_id: Optional[str] = None,
        expired_at=None,
        provider_data: Optional[dict] = None,
    ) -> Optional[AgentSandbox]:
        """Update provider-specific fields on the sandbox record."""
        record = await self.get_by_id(db, sandbox_id)
        if record is None:
            return None
        if status is not None:
            record.status = status
        if provider_sandbox_id is not None:
            record.provider_sandbox_id = provider_sandbox_id
        if expired_at is not None:
            record.expired_at = expired_at
        if provider_data is not None:
            record.provider_data = provider_data
        await db.flush()
        await db.refresh(record)
        return record
