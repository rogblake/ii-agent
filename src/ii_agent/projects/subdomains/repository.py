"""Repository layer for subdomains domain - data access only."""

from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.base import BaseRepository
from ii_agent.projects.subdomains.models import ProjectCustomDomain


class SubdomainRepository(BaseRepository[ProjectCustomDomain]):
    """Data access layer for ProjectCustomDomain model.

    Inherits from BaseRepository: get_by_id, save, update.
    """

    model = ProjectCustomDomain

    async def get_by_project_id(
        self, db: AsyncSession, project_id: uuid.UUID
    ) -> Optional[ProjectCustomDomain]:
        """Get a custom domain by project ID."""
        result = await db.execute(
            select(ProjectCustomDomain).where(ProjectCustomDomain.project_id == project_id)
        )
        return result.scalar_one_or_none()

    async def get_by_subdomain(
        self, db: AsyncSession, subdomain: str
    ) -> Optional[ProjectCustomDomain]:
        """Get a custom domain by subdomain name."""
        result = await db.execute(
            select(ProjectCustomDomain).where(ProjectCustomDomain.subdomain == subdomain)
        )
        return result.scalar_one_or_none()

    async def get_by_full_domain(
        self, db: AsyncSession, full_domain: str
    ) -> Optional[ProjectCustomDomain]:
        """Get a custom domain by full domain URL."""
        result = await db.execute(
            select(ProjectCustomDomain).where(ProjectCustomDomain.full_domain == full_domain)
        )
        return result.scalar_one_or_none()

    async def delete(self, db: AsyncSession, domain: ProjectCustomDomain) -> None:
        """Delete a custom domain record."""
        await db.delete(domain)
        await db.flush()
