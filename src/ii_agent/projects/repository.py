"""Repository layer for projects domain - data access only."""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.repository import BaseRepository
from ii_agent.projects.models import Project


class ProjectRepository(BaseRepository[Project]):
    """Data access layer for Project model."""

    model = Project

    async def get_by_id(self, db: AsyncSession, entity_id: Any) -> Optional[Project]:
        """Get a non-deleted project by its ID (overrides base to filter soft-deletes)."""
        result = await db.execute(
            select(Project).where(
                Project.id == entity_id,
                Project.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_and_user(self, db: AsyncSession, project_id: str, user_id: str) -> Optional[Project]:
        """Get a project by ID for a specific user."""
        result = await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == user_id,
                Project.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_session_id(self, db: AsyncSession, session_id: str) -> Optional[Project]:
        """Get the most recent project for a session."""
        result = await db.execute(
            select(Project)
            .where(
                Project.session_id == session_id,
                Project.deleted_at.is_(None),
            )
            .order_by(Project.updated_at.desc())
        )
        return result.scalars().first()

    async def get_by_session_and_user(self, db: AsyncSession, session_id: str, user_id: str) -> Optional[Project]:
        """Get the most recent project for a session owned by user."""
        result = await db.execute(
            select(Project)
            .where(
                Project.session_id == session_id,
                Project.user_id == user_id,
                Project.deleted_at.is_(None),
            )
            .order_by(Project.updated_at.desc())
        )
        return result.scalars().first()

    async def get_owner_user_id(self, db: AsyncSession, project_id: str) -> Optional[str]:
        """Get the owner user_id for a project."""
        result = await db.execute(
            select(Project.user_id).where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def update_custom_domain(
        self, db: AsyncSession, project_id: str, custom_domain_id: Optional[str], production_url: Optional[str] = None
    ) -> None:
        """Update project's custom_domain_id and optionally production_url."""
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if project:
            project.custom_domain_id = custom_domain_id
            if production_url is not None:
                project.production_url = production_url
            await db.flush()

    async def update_production_url(self, db: AsyncSession, project_id: str, production_url: str) -> None:
        """Update a project's production_url."""
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if project:
            project.production_url = production_url
            await db.flush()
