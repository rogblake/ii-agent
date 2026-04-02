import pytest

from ii_agent.core.exceptions import RunCancelledException
from ii_agent.core.redis.cancel import MemoryRunCancellationManager, RedisRunCancellationManager


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.ttl = {}

    async def setex(self, key, ttl, value):
        self.data[key] = value
        self.ttl[key] = ttl

    async def exists(self, key):
        return 1 if key in self.data else 0

    async def get(self, key):
        return self.data.get(key)

    async def delete(self, key):
        self.data.pop(key, None)

    async def keys(self, pattern):
        prefix = pattern.rstrip("*")
        return [k for k in self.data if k.startswith(prefix)]


@pytest.mark.asyncio
async def test_memory_run_cancellation_lifecycle():
    manager = MemoryRunCancellationManager()

    await manager.register_run("r1")
    assert await manager.is_cancelled("r1") is False

    assert await manager.cancel_run("r1") is True
    assert await manager.is_cancelled("r1") is True

    with pytest.raises(RunCancelledException):
        await manager.raise_if_cancelled("r1")

    await manager.cleanup_run("r1")
    assert await manager.get_active_runs() == {}


@pytest.mark.asyncio
async def test_redis_run_cancellation_manager_namespacing_and_ttl():
    redis = FakeRedis()
    manager = RedisRunCancellationManager(redis_client=redis, namespace="test")

    await manager.register_run("run-1")
    assert redis.ttl["test:run-1"] == manager.RUN_STATE_TTL

    cancelled = await manager.cancel_run("run-1")
    assert cancelled is True
    assert await manager.is_cancelled("run-1") is True

    active = await manager.get_active_runs()
    assert active == {"run-1": True}
