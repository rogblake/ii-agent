"""FastAPI dependencies for subdomains domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.projects.subdomains.exceptions import SubdomainServiceUnavailableError
from ii_agent.projects.dependencies import ProjectRepositoryDep
from ii_agent.projects.deployments.dependencies import DeploymentsRepositoryDep
from ii_agent.projects.subdomains.repository import SubdomainRepository
from ii_agent.projects.subdomains.service import SubdomainService
from ii_agent.projects.subdomains.utils import CloudflareKVConfig, CloudflareKVService


# ==================== Repository Dependencies ====================


def get_subdomain_repository() -> SubdomainRepository:
    """Provide SubdomainRepository instance."""
    return SubdomainRepository()


SubdomainRepositoryDep = Annotated[SubdomainRepository, Depends(get_subdomain_repository)]


# ==================== Service Dependencies ====================


def get_subdomain_service(
    subdomain_repo: SubdomainRepositoryDep,
    project_repo: ProjectRepositoryDep,
    deployments_repo: DeploymentsRepositoryDep,
) -> SubdomainService:
    """Provide SubdomainService instance with explicit repo injection."""
    return SubdomainService(
        subdomain_repo=subdomain_repo,
        project_repo=project_repo,
        deployments_repo=deployments_repo,
        config=get_settings(),
    )


def get_kv_service() -> CloudflareKVService:
    """Provide CloudflareKVService instance from environment config."""
    try:
        config = CloudflareKVConfig.from_env()
        return CloudflareKVService(config)
    except ValueError as e:
        raise SubdomainServiceUnavailableError(
            f"Subdomain service not configured: {str(e)}"
        ) from e


def get_base_domain() -> str:
    """Get base domain from Cloudflare config."""
    try:
        config = CloudflareKVConfig.from_env()
        return config.base_domain
    except ValueError:
        return "iiapp.dev"


SubdomainServiceDep = Annotated[SubdomainService, Depends(get_subdomain_service)]
CloudflareKVServiceDep = Annotated[CloudflareKVService, Depends(get_kv_service)]
BaseDomainDep = Annotated[str, Depends(get_base_domain)]


__all__ = [
    "get_subdomain_repository",
    "get_subdomain_service",
    "SubdomainRepositoryDep",
    "SubdomainServiceDep",
    "get_kv_service",
    "CloudflareKVServiceDep",
    "get_base_domain",
    "BaseDomainDep",
]
