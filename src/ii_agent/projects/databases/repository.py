"""Repository layer for project databases domain - data access only."""

from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.base import BaseRepository
from ii_agent.projects.databases.models import ProjectDatabase


class ProjectDatabaseRepository(BaseRepository[ProjectDatabase]):
    """Data access layer for ProjectDatabase model.

    Inherits from BaseRepository: get_by_id, save, update.
    """

    model = ProjectDatabase

    async def get_active_by_session_id(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
    ) -> Optional[ProjectDatabase]:
        """Get the most recent active database for a session."""
        result = await db.execute(
            select(ProjectDatabase)
            .where(
                ProjectDatabase.session_id == session_id,
                ProjectDatabase.is_active == True,  # noqa: E712
            )
            .order_by(desc(ProjectDatabase.created_at))
        )
        return result.scalars().first()

    async def get_all_by_session_id(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
    ) -> List[ProjectDatabase]:
        """Get all databases for a session."""
        result = await db.execute(
            select(ProjectDatabase)
            .where(ProjectDatabase.session_id == session_id)
            .order_by(desc(ProjectDatabase.created_at))
        )
        return list(result.scalars().all())

    async def deactivate(
        self, db: AsyncSession, database_id: uuid.UUID
    ) -> Optional[ProjectDatabase]:
        """Deactivate a database record (soft delete)."""
        db_record = await self.get_by_id(db, database_id)
        if not db_record:
            return None
        db_record.is_active = False
        return await self.update(db, db_record)

    async def count_active_by_session(self, db: AsyncSession, session_id: uuid.UUID) -> int:
        """Count active databases for a session."""
        result = await db.execute(
            select(func.count(ProjectDatabase.id)).where(
                ProjectDatabase.session_id == session_id,
                ProjectDatabase.is_active == True,  # noqa: E712
            )
        )
        return result.scalar() or 0
