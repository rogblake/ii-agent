"""Secret provider implementations for fetching secrets from various backends."""

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

from ii_agent.core.secrets.keys import SecretKey

logger = logging.getLogger(__name__)


class SecretProvider(ABC):
    """Abstract base class for secret providers."""

    @abstractmethod
    def get_secret(self, key: SecretKey) -> Optional[str]:
        """Fetch a single secret by key.

        Args:
            key: The secret key to fetch

        Returns:
            The secret value, or None if not found
        """
        ...

    def get_secrets(self, keys: set[SecretKey]) -> dict[SecretKey, str]:
        """Fetch multiple secrets.

        Args:
            keys: Set of secret keys to fetch

        Returns:
            Dict mapping found keys to their values (missing keys are omitted)
        """
        result = {}
        for key in keys:
            value = self.get_secret(key)
            if value is not None:
                result[key] = value
        return result


class EnvSecretProvider(SecretProvider):
    """Secret provider that reads from environment variables.

    Used in development and CI where secrets are set as env vars.
    This is effectively a no-op since pydantic-settings already reads env vars,
    but it provides a consistent interface.
    """

    def get_secret(self, key: SecretKey) -> Optional[str]:
        return os.environ.get(key.to_env_var())


class GCPSecretProvider(SecretProvider):
    """Secret provider that reads from GCP Secret Manager.

    Uses in-memory caching to avoid repeated API calls during startup.
    Secrets are fetched once and cached for the lifetime of the provider.
    """

    def __init__(self, project_id: str, prefix: str = "ii-agent"):
        self._project_id = project_id
        self._prefix = prefix
        self._cache: dict[SecretKey, Optional[str]] = {}
        self._client = None

    def _get_client(self):
        """Lazy-initialize the Secret Manager client."""
        if self._client is None:
            try:
                from google.cloud import secretmanager

                self._client = secretmanager.SecretManagerServiceClient()
            except ImportError:
                raise ImportError(
                    "google-cloud-secret-manager is required for GCP secrets. "
                    "Install it with: pip install google-cloud-secret-manager>=2.20.0"
                )
        return self._client

    def get_secret(self, key: SecretKey) -> Optional[str]:
        if key in self._cache:
            return self._cache[key]

        gcp_name = key.to_gcp_name(self._prefix)
        resource_name = f"projects/{self._project_id}/secrets/{gcp_name}/versions/latest"

        try:
            client = self._get_client()
            response = client.access_secret_version(request={"name": resource_name})
            value = response.payload.data.decode("UTF-8")
            self._cache[key] = value
            logger.debug("Loaded secret %s from GCP Secret Manager", gcp_name)
            return value
        except Exception as e:
            logger.warning("Failed to load secret %s from GCP: %s", gcp_name, e)
            self._cache[key] = None
            return None

    def get_secrets(self, keys: set[SecretKey]) -> dict[SecretKey, str]:
        """Fetch multiple secrets, using cache for previously fetched values."""
        result = {}
        for key in keys:
            value = self.get_secret(key)
            if value is not None:
                result[key] = value
        return result
