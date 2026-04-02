"""Redis client singleton.

This module initializes a single Redis client as a module-level singleton
for use across the application. All Redis-dependent services should use
this client.

Import pattern:
    from ii_agent.core.redis import redis_client
"""

import logging
import ssl
from typing import Optional

from redis.asyncio import Redis
from socketio import AsyncRedisManager

from ii_agent.core.config.settings import get_settings

logger = logging.getLogger(__name__)


def _create_redis_client() -> Optional[Redis]:
    """Create Redis client based on configuration.

    Returns:
        Redis client if Redis is enabled, None otherwise.
    """
    settings = get_settings()
    if not settings.redis.session_enabled:
        logger.info("Redis is disabled, using in-memory fallbacks")
        return None

    kwargs = {
        "encoding": "utf-8",
        "retry_on_error": [ConnectionError, TimeoutError],
        "retry_on_timeout": True,
        "max_connections": 30,
        "socket_keepalive": True,
        "socket_connect_timeout": 5,
        "socket_timeout": 5,
        "decode_responses": True,
    }

    if settings.is_redis_ssl:
        kwargs["ssl_cert_reqs"] = ssl.CERT_NONE
        kwargs["ssl_check_hostname"] = False

    return Redis.from_url(url=settings.redis.session_url, **kwargs)


def _create_session_manager() -> Optional[AsyncRedisManager]:
    """Create Socket.IO Redis session manager.

    Returns:
        AsyncRedisManager if Redis is enabled, None otherwise.
    """
    settings = get_settings()
    if not settings.redis.session_enabled:
        return None

    if settings.is_redis_ssl:
        import ssl

        return AsyncRedisManager(
            url=settings.redis.session_url,
            redis_options={
                "ssl_cert_reqs": ssl.CERT_NONE,
                "ssl_check_hostname": False,
                "decode_responses": False,  # Socket.IO requires bytes
            },
        )

    return AsyncRedisManager(
        url=settings.redis.session_url,
        redis_options={"decode_responses": False},  # Socket.IO requires bytes
    )


# Initialize Redis client as module-level singleton
redis_client: Optional[Redis] = _create_redis_client()

# Initialize Socket.IO session manager as module-level singleton
session_manager: Optional[AsyncRedisManager] = _create_session_manager()


async def close_redis() -> None:
    """Close Redis client connection.

    Should be called during application shutdown.
    """
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        logger.info("Redis client connection closed")


def is_redis_enabled() -> bool:
    """Check if Redis is enabled and client is available."""
    return redis_client is not None


__all__ = [
    "redis_client",
    "session_manager",
    "close_redis",
    "is_redis_enabled",
]
