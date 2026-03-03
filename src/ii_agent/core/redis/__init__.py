"""Redis infrastructure module.

Provides centralized Redis client and Redis-based services for:
- Caching (EntityCache)
- Pub/Sub messaging (AsyncIOPubSub)
- Distributed locking (LockFactory)
- Run cancellation management

Import patterns:
    # For Redis client
    from ii_agent.core.redis import redis_client, session_manager, close_redis

    # For caching
    from ii_agent.core.redis import EntityCache, create_entity_cache, entity_cache

    # For pub/sub
    from ii_agent.core.redis import AsyncIOPubSub

    # For distributed locking
    from ii_agent.core.redis import LockFactory

    # For run cancellation
    from ii_agent.core.redis import (
        register_run,
        cancel_run,
        is_cancelled,
        cleanup_run,
        raise_if_cancelled,
        RunCancelledException,
    )
"""

from ii_agent.core.redis.client import (
    redis_client,
    session_manager,
    close_redis,
    is_redis_enabled,
)

from ii_agent.core.redis.cache import (
    EntityCache,
    MemoryEntityCache,
    RedisEntityCache,
    create_entity_cache,
    entity_cache,
)

from ii_agent.core.redis.pubsub import AsyncIOPubSub

from ii_agent.core.redis.lock import LockFactory

from ii_agent.core.redis.cancel import (
    RunCancelledException,
    BaseRunCancellationManager,
    MemoryRunCancellationManager,
    RedisRunCancellationManager,
    register_run,
    cancel_run,
    is_cancelled,
    cleanup_run,
    raise_if_cancelled,
    get_active_runs,
)

from ii_agent.core.redis.detached_tool_results import (
    store_detached_result,
    pop_detached_results,
)

__all__ = [
    # Client
    "redis_client",
    "session_manager",
    "close_redis",
    "is_redis_enabled",
    # Cache
    "EntityCache",
    "MemoryEntityCache",
    "RedisEntityCache",
    "create_entity_cache",
    "entity_cache",
    # Pub/Sub
    "AsyncIOPubSub",
    # Lock
    "LockFactory",
    # Cancel
    "RunCancelledException",
    "BaseRunCancellationManager",
    "MemoryRunCancellationManager",
    "RedisRunCancellationManager",
    "register_run",
    "cancel_run",
    "is_cancelled",
    "cleanup_run",
    "raise_if_cancelled",
    "get_active_runs",
    # Detached tool results
    "store_detached_result",
    "pop_detached_results",
]
