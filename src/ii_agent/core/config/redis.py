"""Redis configuration settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RedisSettings(BaseSettings):
    """Redis configuration for caching and session storage.

    Environment variables:
        REDIS_SESSION_URL: Redis connection URL
        REDIS_SESSION_ENABLED: Enable Redis for sessions
        REDIS_MAX_CONNECTIONS: Maximum connection pool size

    Example:
        REDIS_SESSION_URL=redis://localhost:6379/0
        REDIS_SESSION_ENABLED=true
    """

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    session_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL for session storage and caching",
    )

    session_enabled: bool = Field(
        default=False,
        description="Enable Redis for session storage and caching",
    )

    max_connections: int = Field(
        default=30,
        description="Maximum number of Redis connections in pool",
        ge=1,
    )

    socket_timeout: int = Field(
        default=5,
        description="Socket timeout in seconds",
        ge=1,
    )

    socket_connect_timeout: int = Field(
        default=5,
        description="Socket connect timeout in seconds",
        ge=1,
    )

    decode_responses: bool = Field(
        default=True,
        description="Decode Redis responses to strings",
    )

    # TODO: add is_ssl method check