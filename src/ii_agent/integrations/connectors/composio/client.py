"""Composio SDK client singleton."""

from typing import Optional
from composio import Composio

from ii_agent.core.config.settings import get_settings
from ii_agent.core.logger import logger


class ComposioClient:
    """Singleton wrapper around Composio SDK client."""

    _instance: Optional[Composio] = None

    @classmethod
    def get_client(cls, api_key: Optional[str] = None) -> Composio:
        """Get or create Composio client instance.

        Args:
            api_key: Optional API key override. If not provided, uses config.composio_api_key

        Returns:
            Composio: The Composio SDK client instance

        Raises:
            ValueError: If COMPOSIO_API_KEY is not configured
        """
        if cls._instance is None:
            effective_key = api_key or get_settings().composio_api_key
            if not effective_key:
                raise ValueError(
                    "COMPOSIO_API_KEY not configured. Set COMPOSIO_API_KEY environment variable."
                )

            logger.info("Initializing Composio client")
            cls._instance = Composio(api_key=effective_key)

        return cls._instance

    @classmethod
    def reset(cls):
        """Reset client instance (for testing)."""
        cls._instance = None
