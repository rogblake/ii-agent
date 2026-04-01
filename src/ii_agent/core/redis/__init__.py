"""Redis infrastructure module.

Import patterns::

    from ii_agent.core.redis import get_redis_client, get_session_manager
    from ii_agent.core.redis import EntityCache, get_entity_cache, entity_cache
    from ii_agent.core.redis import LockFactory
    from ii_agent.core.redis import register_run, cancel_run, is_cancelled
"""

from ii_agent.core.redis.client import (
    get_redis_client,
    set_redis_client,
    shutdown_redis_client,
    get_session_manager,
    set_session_manager,
    shutdown_session_manager
)

from ii_agent.core.redis.cache import (
    EntityCache,
    MemoryEntityCache,
    RedisEntityCache,
    TypedEntityCache,
    get_entity_cache,
    create_entity_cache,
)


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


__all__ = [
    # Client
    "get_redis_client",
    "set_redis_client",
    "shutdown_redis_client",
    "shutdown_session_manager"
    "get_session_manager",
    "set_session_manager",
    # Cache
    "EntityCache",
    "MemoryEntityCache",
    "RedisEntityCache",
    "TypedEntityCache",
    "get_entity_cache",
    "create_entity_cache",
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
