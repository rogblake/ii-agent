"""Repository layer for sandboxes domain - data access only."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.agent.sandboxes.models import AgentSandbox


class SandboxRepository:
    """Data access layer for AgentSandbox model."""

    async def get_by_id(self, db: AsyncSession, sandbox_id: uuid.UUID) -> AgentSandbox | None:
        """Get sandbox by internal ID."""
        result = await db.execute(
            select(AgentSandbox).where(AgentSandbox.id == sandbox_id)
        )
        return result.scalars().first()

    async def get_by_session_id(self, db: AsyncSession, session_id: str) -> AgentSandbox | None:
        """Get sandbox by session ID."""
        result = await db.execute(
            select(AgentSandbox).where(AgentSandbox.session_id == session_id)
        )
        return result.scalars().first()

    async def get_by_provider_id(
        self, db: AsyncSession, provider_sandbox_id: str, provider: str = "e2b"
    ) -> AgentSandbox | None:
        """Get sandbox by provider-specific ID."""
        result = await db.execute(
            select(AgentSandbox).where(
                AgentSandbox.provider_sandbox_id == provider_sandbox_id,
                AgentSandbox.provider == provider,
            )
        )
        return result.scalars().first()
