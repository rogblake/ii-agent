"""Subdomain domain enums."""

from enum import StrEnum


class DnsStatus(StrEnum):
    """DNS record status."""

    PENDING = "pending"
    PROPAGATING = "propagating"
    ACTIVE = "active"
    FAILED = "failed"


class SslStatus(StrEnum):
    """SSL certificate status."""

    PENDING = "pending"
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    FAILED = "failed"
