"""Redis client singleton.

Usage::

    from ii_agent.core.redis.client import get_redis_client, get_session_manager

    redis = get_redis_client()       # lazy, returns None if disabled
    manager = get_session_manager()   # lazy, returns None if disabled
"""

import logging
import ssl
from typing import Any, Optional

from redis.asyncio import Redis
from socketio import AsyncRedisManager

from ii_agent.core.config.redis import RedisSettings

logger = logging.getLogger(__name__)

_redis_client: Optional[Redis] = None
_session_manager: Optional[AsyncRedisManager] = None


def _resolve_redis_settings(redis_settings: Optional[RedisSettings] = None) -> RedisSettings:
    """Return provided settings or fall back to the global singleton."""
    if redis_settings is not None:
        return redis_settings
    from ii_agent.core.config.settings import get_settings
    return get_settings().redis


def _create_redis_client(redis_settings: RedisSettings) -> Optional[Redis]:

    kwargs: dict[str, Any] = {
        "encoding": "utf-8",
        "retry_on_error": [ConnectionError, TimeoutError],
        "retry_on_timeout": True,
        "max_connections": redis_settings.max_connections,
        "socket_keepalive": True,
        "socket_connect_timeout": 5,
        "socket_timeout": 5,
        "decode_responses": True,
    }
    url = redis_settings.session_url
    if url.startswith("rediss://"):
        kwargs["ssl_cert_reqs"] = ssl.CERT_NONE
        kwargs["ssl_check_hostname"] = False

    return Redis.from_url(url=url, **kwargs)


def get_redis_client(redis_settings: Optional[RedisSettings] = None) -> Redis:
    """Get the singleton Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = _create_redis_client(_resolve_redis_settings(redis_settings))
    return _redis_client


def set_redis_client(client: Optional[Redis]) -> None:
    """Inject a custom Redis client (for testing)."""
    global _redis_client
    _redis_client = client


async def shutdown_redis_client() -> None:
    """Close and reset the Redis client."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        logger.info("Redis client connection closed")
    _redis_client = None


def _create_session_manager(redis_settings: RedisSettings) -> Optional[AsyncRedisManager]:
    if not redis_settings.session_enabled:
        return None

    url = redis_settings.session_url
    if url.startswith("rediss://"):
        return AsyncRedisManager(
            url=url,
            redis_options={
                "ssl_cert_reqs": ssl.CERT_NONE,
                "ssl_check_hostname": False,
                "decode_responses": False,
            },
        )

    return AsyncRedisManager(
        url=url,
        redis_options={"decode_responses": False},
    )


def get_session_manager(redis_settings: Optional[RedisSettings] = None) -> Optional[AsyncRedisManager]:
    """Get the Socket.IO Redis session manager singleton."""
    global _session_manager
    if _session_manager is None:
        _session_manager = _create_session_manager(_resolve_redis_settings(redis_settings))
    return _session_manager


def set_session_manager(manager: Optional[AsyncRedisManager]) -> None:
    """Inject a custom session manager (for testing)."""
    global _session_manager
    _session_manager = manager


async def shutdown_session_manager() -> None:
    """Close and reset the Redis client."""
    global _session_manager
    if _session_manager is not None:
        await _session_manager.disconnect()
        logger.info("Redis client connection closed")
    _session_manager = None
