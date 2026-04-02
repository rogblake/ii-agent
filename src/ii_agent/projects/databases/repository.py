"""Repository layer for project databases domain - data access only."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.projects.databases.models import ProjectDatabase


class ProjectDatabaseRepository:
    """Data access layer for ProjectDatabase model."""

    async def create(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        source: str,
        connection_string: str,
        host: Optional[str] = None,
        database_name: Optional[str] = None,
        role_name: Optional[str] = None,
        branch_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProjectDatabase:
        """Create a new database record for a session."""
        db_record = ProjectDatabase(
            id=str(uuid.uuid4()),
            session_id=session_id,
            source=source,
            connection_string=connection_string,
            host=host,
            database_name=database_name,
            role_name=role_name,
            branch_name=branch_name,
            db_metadata=metadata,
            is_active=True,
        )
        db.add(db_record)
        await db.flush()
        await db.refresh(db_record)
        return db_record

    async def get_active_by_session_id(
        self,
        db: AsyncSession,
        session_id: str,
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
        session_id: str,
    ) -> List[ProjectDatabase]:
        """Get all databases for a session."""
        result = await db.execute(
            select(ProjectDatabase)
            .where(ProjectDatabase.session_id == session_id)
            .order_by(desc(ProjectDatabase.created_at))
        )
        return list(result.scalars().all())

    async def get_by_id(
        self,
        db: AsyncSession,
        database_id: str,
    ) -> Optional[ProjectDatabase]:
        """Get a database by its ID."""
        result = await db.execute(
            select(ProjectDatabase).where(ProjectDatabase.id == database_id)
        )
        return result.scalar_one_or_none()

    async def update(self, db: AsyncSession, db_record: ProjectDatabase) -> ProjectDatabase:
        """Flush and refresh an existing database record."""
        await db.flush()
        await db.refresh(db_record)
        return db_record

    async def deactivate(self, db: AsyncSession, database_id: str) -> Optional[ProjectDatabase]:
        """Deactivate a database record (soft delete)."""
        db_record = await self.get_by_id(db, database_id)
        if not db_record:
            return None
        db_record.is_active = False
        return await self.update(db, db_record)

    async def count_active_by_session(self, db: AsyncSession, session_id: str) -> int:
        """Count active databases for a session."""
        result = await db.execute(
            select(func.count(ProjectDatabase.id)).where(
                ProjectDatabase.session_id == session_id,
                ProjectDatabase.is_active == True,  # noqa: E712
            )
        )
        return result.scalar() or 0

