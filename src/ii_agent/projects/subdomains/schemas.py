"""Pydantic schemas (DTOs) for subdomains domain."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ii_agent.projects.subdomains.types import DnsStatus, SslStatus


class CheckAvailabilityRequest(BaseModel):
    """Request to check subdomain availability."""

    subdomain: str = Field(
        ...,
        description="The subdomain to check (e.g., 'myapp' for myapp.iiapp.dev)",
        min_length=2,
        max_length=63,
    )


class ClaimSubdomainRequest(BaseModel):
    """Request to claim a custom subdomain for a project."""

    project_id: UUID = Field(
        ...,
        description="The project ID to claim the subdomain for",
    )
    subdomain: str = Field(
        ...,
        description="The subdomain to claim (e.g., 'myapp' for myapp.iiapp.dev)",
        min_length=2,
        max_length=63,
    )


class ClaimSubdomainResponse(BaseModel):
    """Response for subdomain claim operation."""

    success: bool
    subdomain: Optional[str] = None
    full_domain: Optional[str] = None
    production_url: Optional[str] = None
    error: Optional[str] = None


class CheckAvailabilityResponse(BaseModel):
    """Response for availability check."""

    subdomain: str
    available: bool
    full_domain: Optional[str] = None
    error: Optional[str] = None
    suggestions: Optional[list[str]] = None


class SubdomainResponse(BaseModel):
    """Response for subdomain operations."""

    success: bool
    subdomain: Optional[str] = None
    full_domain: Optional[str] = None
    status: Optional[str] = None
    cloud_run_url: Optional[str] = None
    error: Optional[str] = None


class SubdomainListResponse(BaseModel):
    """Response for listing subdomains."""

    success: bool
    subdomains: list[SubdomainResponse]
    total: int
    page: int
    per_page: int


class ReservedSubdomainsResponse(BaseModel):
    """Response listing reserved subdomains."""

    reserved: list[str]


class CustomDomainResponse(BaseModel):
    """Serialized custom domain record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    subdomain: str
    full_domain: str
    deployment_id: Optional[UUID] = None
    dns_status: Optional[DnsStatus] = None
    ssl_status: Optional[SslStatus] = None
    cloudflare_record_id: Optional[str] = None
    claimed_at: Optional[datetime] = None
    claimed_by_user_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
