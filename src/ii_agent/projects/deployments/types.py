"""Deployment domain enums."""

from enum import StrEnum


class DeploymentStatus(StrEnum):
    """Deployment lifecycle status."""

    PENDING = "pending"
    BUILDING = "building"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    FAILED = "failed"


class DeploymentProvider(StrEnum):
    """Deployment platform."""

    CLOUD_RUN = "cloud_run"
    VERCEL = "vercel"
