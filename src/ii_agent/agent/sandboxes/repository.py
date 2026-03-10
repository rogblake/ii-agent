"""Repository layer for sandboxes domain - data access only."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.agent.sandboxes.models import Sandbox


class SandboxRepository:
    """Data access layer for Sandbox model."""

    async def get_by_id(self, db: AsyncSession, sandbox_id: uuid.UUID) -> Sandbox | None:
        """Get sandbox by internal ID."""
        result = await db.execute(
            select(Sandbox).where(Sandbox.id == sandbox_id)
        )
        return result.scalars().first()

    async def get_by_session_id(self, db: AsyncSession, session_id: str) -> Sandbox | None:
        """Get sandbox by session ID."""
        result = await db.execute(
            select(Sandbox).where(Sandbox.session_id == session_id)
        )
        return result.scalars().first()

    async def get_by_provider_id(
        self, db: AsyncSession, provider_sandbox_id: str, provider: str = "e2b"
    ) -> Sandbox | None:
        """Get sandbox by provider-specific ID."""
        result = await db.execute(
            select(Sandbox).where(
                Sandbox.provider_sandbox_id == provider_sandbox_id,
                Sandbox.provider == provider,
            )
        )
        return result.scalars().first()
