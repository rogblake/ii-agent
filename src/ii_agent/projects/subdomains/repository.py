"""Repository layer for subdomains domain - data access only."""

from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.projects.subdomains.models import ProjectCustomDomain


class SubdomainRepository:
    """Data access layer for ProjectCustomDomain model."""

    async def get_by_project_id(self, db: AsyncSession, project_id: str) -> Optional[ProjectCustomDomain]:
        """Get a custom domain by project ID."""
        result = await db.execute(
            select(ProjectCustomDomain).where(
                ProjectCustomDomain.project_id == project_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_subdomain(self, db: AsyncSession, subdomain: str) -> Optional[ProjectCustomDomain]:
        """Get a custom domain by subdomain name."""
        result = await db.execute(
            select(ProjectCustomDomain).where(
                ProjectCustomDomain.subdomain == subdomain
            )
        )
        return result.scalar_one_or_none()

    async def get_by_full_domain(self, db: AsyncSession, full_domain: str) -> Optional[ProjectCustomDomain]:
        """Get a custom domain by full domain URL."""
        result = await db.execute(
            select(ProjectCustomDomain).where(
                ProjectCustomDomain.full_domain == full_domain
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        db: AsyncSession,
        *,
        project_id: str,
        user_id: str,
        subdomain: str,
        full_domain: str,
        deployment_id: Optional[str] = None,
        cloudflare_record_id: Optional[str] = None,
    ) -> ProjectCustomDomain:
        """Create a new custom domain record."""
        custom_domain = ProjectCustomDomain(
            id=str(uuid.uuid4()),
            project_id=project_id,
            subdomain=subdomain,
            full_domain=full_domain,
            deployment_id=deployment_id,
            dns_status="active",
            ssl_status="active",
            cloudflare_record_id=cloudflare_record_id,
            claimed_at=datetime.now(timezone.utc),
            claimed_by_user_id=user_id,
        )
        db.add(custom_domain)
        await db.flush()
        await db.refresh(custom_domain)
        return custom_domain

    async def update(self, db: AsyncSession, domain: ProjectCustomDomain) -> ProjectCustomDomain:
        """Flush and refresh an updated domain record."""
        await db.flush()
        await db.refresh(domain)
        return domain

    async def delete(self, db: AsyncSession, domain: ProjectCustomDomain) -> None:
        """Delete a custom domain record."""
        await db.delete(domain)
        await db.flush()
