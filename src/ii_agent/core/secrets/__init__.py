"""GCP Secret Manager integration for ii-agent configuration.

This module provides a pluggable secret provider system:
- EnvSecretProvider: Reads from environment variables (dev/CI)
- GCPSecretProvider: Reads from GCP Secret Manager with caching (production)

GCP secrets are loaded automatically during Settings construction via
GCPSecretManagerSource (a custom Pydantic settings source). No manual
loading or lifespan hooks needed — just set GCP_PROJECT_ID env var.

Usage (manual, for scripts or testing):
    from ii_agent.core.secrets import GCPSecretProvider, load_secrets

    provider = GCPSecretProvider(project_id="my-project")
    secrets = load_secrets(provider)
"""

from ii_agent.core.secrets.keys import (
    SecretKey,
    ALL_SECRETS,
    DATABASE_SECRETS,
    OAUTH_SECRETS,
    BILLING_SECRETS,
    LLM_SECRETS,
    TOOL_SERVER_SECRETS,
    COMPOSIO_SECRETS,
)
from ii_agent.core.secrets.provider import (
    SecretProvider,
    EnvSecretProvider,
    GCPSecretProvider,
)
from ii_agent.core.secrets.loader import load_secrets

__all__ = [
    "SecretKey",
    "SecretProvider",
    "EnvSecretProvider",
    "GCPSecretProvider",
    "load_secrets",
    "ALL_SECRETS",
    "DATABASE_SECRETS",
    "OAUTH_SECRETS",
    "BILLING_SECRETS",
    "LLM_SECRETS",
    "TOOL_SERVER_SECRETS",
    "COMPOSIO_SECRETS",
]
