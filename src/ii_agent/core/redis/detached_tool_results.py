"""Detached tool result storage.

When a run is cancelled, in-flight tools are "detached" — they keep running
in the background.  Once they finish, results are stored here (keyed by
session_id) so the *next* agent loop iteration can inject them as context.

Import pattern:
    from ii_agent.core.redis import store_detached_result, pop_detached_results
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseDetachedToolResultStore(ABC):
    """Interface for storing / retrieving detached tool results."""

    @abstractmethod
    async def store_result(
        self, session_id: str, call_id: str, tool_name: str, result: str
    ) -> None:
        """Persist one completed detached-tool result."""

    @abstractmethod
    async def pop_results(self, session_id: str) -> List[Dict[str, Any]]:
        """Return *all* stored results for *session_id* and clear them."""


# ---------------------------------------------------------------------------
# In-memory implementation (single-process / dev)
# ---------------------------------------------------------------------------

class MemoryDetachedToolResultStore(BaseDetachedToolResultStore):
    """In-memory store.  Only works within a single process."""

    def __init__(self) -> None:
        self._store: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def store_result(
        self, session_id: str, call_id: str, tool_name: str, result: str
    ) -> None:
        entry = {
            "call_id": call_id,
            "tool_name": tool_name,
            "result": result,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        async with self._lock:
            self._store.setdefault(session_id, []).append(entry)
        logger.info("Detached tool %s result stored in memory for session %s", tool_name, session_id)

    async def pop_results(self, session_id: str) -> List[Dict[str, Any]]:
        async with self._lock:
            return self._store.pop(session_id, [])


# ---------------------------------------------------------------------------
# Redis implementation (multi-worker safe)
# ---------------------------------------------------------------------------

class RedisDetachedToolResultStore(BaseDetachedToolResultStore):
    """Redis LIST-backed store.  RPUSH is atomic so concurrent writers are safe."""

    RESULT_TTL = 86400  # 24 hours

    def __init__(self, redis_client: Redis, namespace: str = "detached_results") -> None:
        self._redis = redis_client
        self._namespace = namespace

    def _make_key(self, session_id: str) -> str:
        return f"{self._namespace}:{session_id}"

    async def store_result(
        self, session_id: str, call_id: str, tool_name: str, result: str
    ) -> None:
        entry = json.dumps({
            "call_id": call_id,
            "tool_name": tool_name,
            "result": result,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            key = self._make_key(session_id)
            await self._redis.rpush(key, entry)
            await self._redis.expire(key, self.RESULT_TTL)
            logger.info("Detached tool %s result stored in Redis for session %s", tool_name, session_id)
        except Exception as e:
            logger.error("Failed to store detached result for session %s: %s", session_id, e, exc_info=True)

    async def pop_results(self, session_id: str) -> List[Dict[str, Any]]:
        try:
            key = self._make_key(session_id)
            pipe = self._redis.pipeline()
            pipe.lrange(key, 0, -1)
            pipe.delete(key)
            raw_results, _ = await pipe.execute()
            return [json.loads(r) for r in raw_results]
        except Exception as e:
            logger.error("Failed to pop detached results for session %s: %s", session_id, e, exc_info=True)
            return []


# ---------------------------------------------------------------------------
# Factory & singleton
# ---------------------------------------------------------------------------

def _create_store() -> BaseDetachedToolResultStore:
    """Create store based on Redis availability."""
    try:
        from ii_agent.core.config.settings import get_settings
        from ii_agent.core.redis.client import redis_client

        if get_settings().redis.session_enabled and redis_client is not None:
            logger.info("Using Redis-based detached tool result store")
            return RedisDetachedToolResultStore(redis_client=redis_client)
        else:
            logger.info("Using in-memory detached tool result store")
            return MemoryDetachedToolResultStore()
    except Exception as e:
        logger.warning("Failed to init Redis detached tool result store, falling back to memory: %s", e)
        return MemoryDetachedToolResultStore()


_store = _create_store()


# ---------------------------------------------------------------------------
# Public module-level API
# ---------------------------------------------------------------------------

async def store_detached_result(
    session_id: str, call_id: str, tool_name: str, result: str
) -> None:
    """Store a completed detached-tool result for later injection."""
    await _store.store_result(session_id, call_id, tool_name, result)


async def pop_detached_results(session_id: str) -> List[Dict[str, Any]]:
    """Pop all completed detached-tool results for a session (returns [] if none)."""
    return await _store.pop_results(session_id)


__all__ = [
    "BaseDetachedToolResultStore",
    "MemoryDetachedToolResultStore",
    "RedisDetachedToolResultStore",
    "store_detached_result",
    "pop_detached_results",
]
