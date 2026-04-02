"""Distributed lock factory using Redis or asyncio.

Import pattern:
    from ii_agent.core.redis import LockFactory
"""

import asyncio
from typing import Optional, Union

from redis.asyncio.lock import Lock

from ii_agent.core.config.settings import get_settings


class LockFactory:
    """Simple factory for creating distributed or local locks."""

    @staticmethod
    def get_lock(
        key: str,
        timeout: Optional[float] = None,
        namespace: str = "default",
    ) -> Union[asyncio.Lock, Lock]:
        """Get a lock instance - Redis lock if enabled, asyncio.Lock otherwise.

        Args:
            key: Lock key
            timeout: Lock timeout in seconds (for Redis locks)
            namespace: Namespace for Redis locks

        Returns:
            Redis lock or asyncio.Lock instance
        """
        from ii_agent.core.redis.client import redis_client

        if get_settings().redis.session_enabled and redis_client is not None:
            # Return Redis lock for distributed locking
            lock_key = f"lock:{namespace}:{key}"
            return redis_client.lock(lock_key, timeout=timeout)
        else:
            # Return asyncio.Lock for local locking
            return asyncio.Lock()


__all__ = ["LockFactory"]
