"""Subdomain management domain module."""

from ii_agent.projects.subdomains.models import ProjectCustomDomain
from ii_agent.projects.subdomains.repository import SubdomainRepository
from ii_agent.projects.subdomains.service import SubdomainService
from ii_agent.projects.subdomains.router import router
from ii_agent.projects.subdomains.schemas import (
    CheckAvailabilityRequest,
    CheckAvailabilityResponse,
    ClaimSubdomainRequest,
    ClaimSubdomainResponse,
    CustomDomainResponse,
    SubdomainResponse,
    SubdomainListResponse,
    ReservedSubdomainsResponse,
)
from ii_agent.projects.subdomains.utils import (
    CloudflareKVConfig,
    CloudflareKVService,
    SubdomainStatus,
    SubdomainResult,
    RESERVED_SUBDOMAINS,
    validate_subdomain,
    create_subdomain_route,
    check_subdomain_availability,
)
from ii_agent.projects.subdomains.exceptions import (
    SubdomainNotFoundError,
    SubdomainNotAvailableError,
    SubdomainServiceUnavailableError,
)

__all__ = [
    # Models
    "ProjectCustomDomain",
    # Repository
    "SubdomainRepository",
    # Service
    "SubdomainService",
    # Router
    "router",
    # Schemas
    "CheckAvailabilityRequest",
    "CheckAvailabilityResponse",
    "ClaimSubdomainRequest",
    "ClaimSubdomainResponse",
    "CustomDomainResponse",
    "SubdomainResponse",
    "SubdomainListResponse",
    "ReservedSubdomainsResponse",
    # Utils (Cloudflare KV)
    "CloudflareKVConfig",
    "CloudflareKVService",
    "SubdomainStatus",
    "SubdomainResult",
    "RESERVED_SUBDOMAINS",
    "validate_subdomain",
    "create_subdomain_route",
    "check_subdomain_availability",
    # Exceptions
    "SubdomainNotFoundError",
    "SubdomainNotAvailableError",
    "SubdomainServiceUnavailableError",
]
