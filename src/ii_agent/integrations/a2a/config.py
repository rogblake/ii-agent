"""A2A Server Configuration."""

import logging
from typing import Any, Dict

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class A2AConfig(BaseSettings):
    """A2A Server Configuration following ii-agent patterns."""

    model_config = SettingsConfigDict(
        env_prefix="A2A_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Server configuration
    server_host: str = Field(default="0.0.0.0", description="Host to bind the server")
    server_port: int = Field(
        default=11002, description="Port to bind the server", ge=1, le=65535
    )

    # Runtime configuration
    log_level: str = Field(default="info", description="Log level")
    max_workers: int = Field(
        default=1,
        description="Maximum worker processes for the A2A service",
        ge=1,
    )
    timeout: int = Field(default=300, description="Request timeout in seconds", ge=1)

    # Third-party A2A agents configuration
    third_party_agents: str = Field(
        default="{}",
        description="JSON string containing third-party A2A agents configuration",
    )

    # Authentication
    allowed_api_keys: str = Field(
        default="",
        description="Comma-separated list of API keys allowed to access the A2A server",
    )

    # Public-facing URL (optional)
    public_base_url: str | None = Field(
        default=None,
        description=(
            "Externally accessible base URL for the A2A server; when provided, Agent Card URLs"
            " and log messages will use this value instead of constructing from server_host/server_port."
        ),
    )

    def get_third_party_agents(self) -> Dict[str, Any]:
        """Parse and return third-party agents configuration as a dictionary."""
        import json

        try:
            data = json.loads(self.third_party_agents)
        except (json.JSONDecodeError, TypeError):
            return {}

        if isinstance(data, dict):
            return data

        logger.warning(
            "A2A third-party agents config must be a JSON object; got %s",
            type(data),
        )
        return {}

    def set_third_party_agents(self, agents: Dict[str, Any]) -> None:
        """Set third-party agents configuration from a dictionary."""
        import json

        self.third_party_agents = json.dumps(agents, ensure_ascii=False)
        os_key = "A2A_THIRD_PARTY_AGENTS"
        try:
            import os

            os.environ[os_key] = self.third_party_agents
        except (
            Exception
        ):  # pragma: no cover - defensive path when os.getenv unavailable
            pass
