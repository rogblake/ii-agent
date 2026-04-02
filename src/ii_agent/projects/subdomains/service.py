"""Service layer for subdomains domain - business logic only."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.core.logger import logger

from ii_agent.projects.repository import ProjectRepository
from ii_agent.projects.deployments.repository import DeploymentsRepository
from ii_agent.projects.subdomains.exceptions import SubdomainNotFoundError
from ii_agent.projects.subdomains.models import ProjectCustomDomain
from ii_agent.projects.subdomains.repository import SubdomainRepository
from ii_agent.projects.subdomains.schemas import CustomDomainResponse


class SubdomainService:
    """Service for managing custom subdomains - business logic layer."""

    def __init__(
        self,
        *,
        subdomain_repo: SubdomainRepository,
        project_repo: ProjectRepository,
        deployments_repo: DeploymentsRepository,
        config: Settings,
    ) -> None:
        self._config = config
        self._subdomain_repo = subdomain_repo
        self._project_repo = project_repo
        self._deployments_repo = deployments_repo

    async def create_or_update_custom_domain(
        self,
        db: AsyncSession,
        *,
        project_id: str,
        user_id: str,
        subdomain: str,
        full_domain: str,
        deployment_id: Optional[str] = None,
        cloudflare_record_id: Optional[str] = None,
    ) -> CustomDomainResponse:
        """Create a custom domain record for a project, or update if one exists."""
        existing = await self._subdomain_repo.get_by_project_id(db, project_id)

        if existing:
            existing.subdomain = subdomain
            existing.full_domain = full_domain
            existing.deployment_id = deployment_id
            existing.cloudflare_record_id = cloudflare_record_id
            existing.claimed_at = datetime.now(timezone.utc)
            existing.claimed_by_user_id = user_id
            existing.dns_status = "active"
            existing.ssl_status = "active"

            domain = await self._subdomain_repo.update(db, existing)

            await self._project_repo.update_custom_domain(
                db, project_id, domain.id, full_domain
            )

            return CustomDomainResponse.model_validate(domain)

        domain = await self._subdomain_repo.create(
            db,
            project_id=project_id,
            user_id=user_id,
            subdomain=subdomain,
            full_domain=full_domain,
            deployment_id=deployment_id,
            cloudflare_record_id=cloudflare_record_id,
        )

        await self._project_repo.update_custom_domain(
            db, project_id, domain.id, full_domain
        )

        return CustomDomainResponse.model_validate(domain)

    async def delete_custom_domain(
        self,
        db: AsyncSession,
        *,
        project_id: str,
        user_id: str,
    ) -> bool:
        """Delete a custom domain for a project.

        Returns True if deleted, False if not found.
        """
        project = await self._project_repo.get_by_id_and_user(db, project_id, user_id)
        if not project:
            return False

        domain = await self._subdomain_repo.get_by_project_id(db, project_id)
        if not domain:
            return False

        await self._project_repo.update_custom_domain(db, project_id, None)

        # Revert production_url to the current deployment URL
        if project.current_production_deployment_id:
            deployment = await self._deployments_repo.get_latest_deployment(
                db, project_id=project_id
            )
            if deployment and deployment.deployment_url:
                await self._project_repo.update_production_url(
                    db, project_id, deployment.deployment_url
                )

        await self._subdomain_repo.delete(db, domain)

        return True

    async def get_subdomain_record(
        self,
        db: AsyncSession,
        subdomain: str,
        *,
        user_id: str,
        is_admin: bool = False,
    ) -> Optional[ProjectCustomDomain]:
        """Get a subdomain record, enforcing ownership for non-admin users."""
        subdomain = subdomain.lower().strip()

        domain = await self._subdomain_repo.get_by_subdomain(db, subdomain)
        if not domain:
            return None

        if is_admin:
            return domain

        # Verify the user owns the project this domain belongs to
        project = await self._project_repo.get_by_id_and_user(db, domain.project_id, user_id)
        if not project:
            return None

        return domain

    async def get_custom_domain_by_subdomain(
        self, db: AsyncSession, subdomain: str
    ) -> Optional[CustomDomainResponse]:
        """Get a custom domain by subdomain name."""
        domain = await self._subdomain_repo.get_by_subdomain(db, subdomain)
        if not domain:
            return None
        return CustomDomainResponse.model_validate(domain)

    async def get_custom_domain_by_full_domain(
        self, db: AsyncSession, full_domain: str
    ) -> Optional[CustomDomainResponse]:
        """Get a custom domain by full domain URL."""
        domain = await self._subdomain_repo.get_by_full_domain(db, full_domain)
        if not domain:
            return None
        return CustomDomainResponse.model_validate(domain)

    async def get_project_owner_user_id(self, db: AsyncSession, project_id: str) -> Optional[str]:
        """Get the owner user_id for a project."""
        return await self._project_repo.get_owner_user_id(db, project_id)

    async def get_cloud_run_url(self, db: AsyncSession, project_id: str) -> Optional[str]:
        """Get the Cloud Run deployment URL for a project."""
        deployment = await self._deployments_repo.get_latest_deployment(
            db, project_id=project_id, provider="cloud_run"
        )
        if not deployment:
            return None
        return deployment.deployment_url

    async def get_user_project(self, db: AsyncSession, project_id: str, user_id: str):
        """Verify user owns the project and return it."""
        return await self._project_repo.get_by_id_and_user(db, project_id, user_id)
