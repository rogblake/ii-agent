"""Unit tests for core/redis/cache.py (r4)."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# MemoryEntityCache
# ---------------------------------------------------------------------------

class TestMemoryEntityCacheR4:
    def _make_cache(self, namespace: str = "test", max_size: int = 100):
        from ii_agent.core.redis.cache import MemoryEntityCache
        return MemoryEntityCache(namespace=namespace, max_size=max_size)

    @pytest.mark.asyncio
    async def test_set_and_get_dict_value(self):
        cache = self._make_cache()
        await cache.set("key1", {"foo": "bar"})
        result = await cache.get("key1")
        assert result == {"foo": "bar"}

    @pytest.mark.asyncio
    async def test_set_and_get_string_value(self):
        cache = self._make_cache()
        value = json.dumps({"hello": "world"})
        await cache.set("key1", value)
        result = await cache.get("key1")
        assert result == {"hello": "world"}

    @pytest.mark.asyncio
    async def test_get_missing_key_returns_none(self):
        cache = self._make_cache()
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_with_ttl_expires(self):
        cache = self._make_cache()
        await cache.set("expiring", {"value": "x"}, ttl=1)
        # Patch time to be in the future
        result = await cache.get("expiring")
        assert result is not None  # Not expired yet

        # Manually set expired_at in the past
        key = cache._make_key("expiring")
        cache._cache[key]["expires_at"] = time.time() - 10
        result = await cache.get("expiring")
        assert result is None

    @pytest.mark.asyncio
    async def test_evict_existing_key_returns_true(self):
        cache = self._make_cache()
        await cache.set("to_evict", {"data": 1})
        result = await cache.evict("to_evict")
        assert result is True
        assert await cache.get("to_evict") is None

    @pytest.mark.asyncio
    async def test_evict_nonexistent_key_returns_false(self):
        cache = self._make_cache()
        result = await cache.evict("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_returns_true_for_present_key(self):
        cache = self._make_cache()
        await cache.set("exists_key", {"x": 1})
        assert await cache.exists("exists_key") is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_for_missing_key(self):
        cache = self._make_cache()
        assert await cache.exists("missing") is False

    @pytest.mark.asyncio
    async def test_exists_returns_false_for_expired_key(self):
        cache = self._make_cache()
        await cache.set("exp_key", {"x": 1}, ttl=5)
        key = cache._make_key("exp_key")
        cache._cache[key]["expires_at"] = time.time() - 1
        assert await cache.exists("exp_key") is False

    @pytest.mark.asyncio
    async def test_clear_removes_namespace_keys(self):
        from ii_agent.core.redis.cache import MemoryEntityCache
        cache = MemoryEntityCache(namespace="test")
        # Manually insert keys that match the clear pattern
        cache._cache["cache:test:key1"] = {"value": {"x": 1}, "expires_at": None}
        cache._cache["cache:test:key2"] = {"value": {"y": 2}, "expires_at": None}
        result = await cache.clear()
        assert result is True
        assert "cache:test:key1" not in cache._cache
        assert "cache:test:key2" not in cache._cache

    @pytest.mark.asyncio
    async def test_close_clears_all_cache(self):
        cache = self._make_cache()
        await cache.set("k1", {"v": 1})
        await cache.close()
        assert len(cache._cache) == 0

    @pytest.mark.asyncio
    async def test_max_size_evicts_oldest(self):
        cache = self._make_cache(max_size=3)
        await cache.set("k1", {"x": 1})
        await cache.set("k2", {"x": 2})
        await cache.set("k3", {"x": 3})
        # Adding 4th should evict the oldest (k1)
        await cache.set("k4", {"x": 4})
        assert len(cache._cache) == 3
        # k1 should be gone
        assert await cache.get("k1") is None

    @pytest.mark.asyncio
    async def test_get_moves_key_to_end_lru(self):
        cache = self._make_cache(max_size=3)
        await cache.set("k1", {"x": 1})
        await cache.set("k2", {"x": 2})
        # Access k1 to move it to end (most recent)
        await cache.get("k1")
        await cache.set("k3", {"x": 3})
        await cache.set("k4", {"x": 4})  # Should evict k2 (now oldest)
        # k1 was recently accessed, should still be present
        assert await cache.get("k1") is not None

    def test_get_namespace(self):
        cache = self._make_cache(namespace="myns")
        assert cache.get_namespace() == "myns"

    def test_make_key_format(self):
        cache = self._make_cache(namespace="myns")
        assert cache._make_key("thekey") == "myns:thekey"

    @pytest.mark.asyncio
    async def test_set_returns_true_on_success(self):
        cache = self._make_cache()
        result = await cache.set("k", {"v": 1})
        assert result is True

    @pytest.mark.asyncio
    async def test_set_without_ttl_no_expiry(self):
        cache = self._make_cache()
        await cache.set("no_ttl", {"x": 1}, ttl=None)
        key = cache._make_key("no_ttl")
        assert cache._cache[key]["expires_at"] is None


# ---------------------------------------------------------------------------
# RedisEntityCache
# ---------------------------------------------------------------------------

class TestRedisEntityCacheR4:
    def _make_redis_cache(self, namespace: str = "test", default_ttl: int = 3600):
        from ii_agent.core.redis.cache import RedisEntityCache
        mock_redis = AsyncMock()
        return RedisEntityCache(redis_client=mock_redis, namespace=namespace, default_ttl=default_ttl), mock_redis

    @pytest.mark.asyncio
    async def test_get_returns_parsed_json(self):
        cache, mock_redis = self._make_redis_cache()
        mock_redis.get = AsyncMock(return_value=json.dumps({"key": "value"}))
        result = await cache.get("mykey")
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing(self):
        cache, mock_redis = self._make_redis_cache()
        mock_redis.get = AsyncMock(return_value=None)
        result = await cache.get("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_handles_redis_exception(self):
        cache, mock_redis = self._make_redis_cache()
        mock_redis.get = AsyncMock(side_effect=Exception("Redis down"))
        result = await cache.get("key")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_dict_serializes_to_json(self):
        cache, mock_redis = self._make_redis_cache()
        mock_redis.setex = AsyncMock(return_value=True)
        result = await cache.set("mykey", {"foo": "bar"})
        assert result is True
        mock_redis.setex.assert_called_once()
        call_kwargs = mock_redis.setex.call_args
        # Verify JSON was passed
        value_arg = call_kwargs[1].get("value") or call_kwargs[0][2]
        parsed = json.loads(value_arg)
        assert parsed == {"foo": "bar"}

    @pytest.mark.asyncio
    async def test_set_string_not_re_serialized(self):
        cache, mock_redis = self._make_redis_cache()
        mock_redis.setex = AsyncMock(return_value=True)
        await cache.set("mykey", '{"already": "json"}')
        call_kwargs = mock_redis.setex.call_args
        value_arg = call_kwargs[1].get("value") or call_kwargs[0][2]
        assert value_arg == '{"already": "json"}'

    @pytest.mark.asyncio
    async def test_set_uses_default_ttl_when_none(self):
        cache, mock_redis = self._make_redis_cache(default_ttl=7200)
        mock_redis.setex = AsyncMock(return_value=True)
        await cache.set("k", {"v": 1}, ttl=None)
        call_kwargs = mock_redis.setex.call_args
        time_arg = call_kwargs[1].get("time") or call_kwargs[0][1]
        assert time_arg == 7200

    @pytest.mark.asyncio
    async def test_set_uses_provided_ttl(self):
        cache, mock_redis = self._make_redis_cache(default_ttl=7200)
        mock_redis.setex = AsyncMock(return_value=True)
        await cache.set("k", {"v": 1}, ttl=300)
        call_kwargs = mock_redis.setex.call_args
        time_arg = call_kwargs[1].get("time") or call_kwargs[0][1]
        assert time_arg == 300

    @pytest.mark.asyncio
    async def test_set_returns_false_on_exception(self):
        cache, mock_redis = self._make_redis_cache()
        mock_redis.setex = AsyncMock(side_effect=Exception("Redis error"))
        result = await cache.set("k", {"v": 1})
        assert result is False

    @pytest.mark.asyncio
    async def test_evict_returns_true_when_deleted(self):
        cache, mock_redis = self._make_redis_cache()
        mock_redis.delete = AsyncMock(return_value=1)
        result = await cache.evict("key")
        assert result is True

    @pytest.mark.asyncio
    async def test_evict_returns_false_when_not_found(self):
        cache, mock_redis = self._make_redis_cache()
        mock_redis.delete = AsyncMock(return_value=0)
        result = await cache.evict("missing")
        assert result is False

    @pytest.mark.asyncio
    async def test_evict_handles_exception(self):
        cache, mock_redis = self._make_redis_cache()
        mock_redis.delete = AsyncMock(side_effect=Exception("Redis down"))
        result = await cache.evict("key")
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_returns_true_when_key_exists(self):
        cache, mock_redis = self._make_redis_cache()
        mock_redis.exists = AsyncMock(return_value=1)
        result = await cache.exists("key")
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_when_key_missing(self):
        cache, mock_redis = self._make_redis_cache()
        mock_redis.exists = AsyncMock(return_value=0)
        result = await cache.exists("key")
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_handles_exception(self):
        cache, mock_redis = self._make_redis_cache()
        mock_redis.exists = AsyncMock(side_effect=Exception("Redis down"))
        result = await cache.exists("key")
        assert result is False

    @pytest.mark.asyncio
    async def test_clear_deletes_matching_keys(self):
        cache, mock_redis = self._make_redis_cache(namespace="myns")
        mock_redis.keys = AsyncMock(return_value=["cache:myns:k1", "cache:myns:k2"])
        mock_redis.delete = AsyncMock(return_value=2)
        result = await cache.clear()
        assert result is True
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_no_keys_returns_true(self):
        cache, mock_redis = self._make_redis_cache()
        mock_redis.keys = AsyncMock(return_value=[])
        result = await cache.clear()
        assert result is True

    @pytest.mark.asyncio
    async def test_clear_handles_exception(self):
        cache, mock_redis = self._make_redis_cache()
        mock_redis.keys = AsyncMock(side_effect=Exception("Redis down"))
        result = await cache.clear()
        assert result is False

    @pytest.mark.asyncio
    async def test_close_is_noop(self):
        cache, mock_redis = self._make_redis_cache()
        # Should not raise
        await cache.close()

    def test_make_key_format(self):
        from ii_agent.core.redis.cache import RedisEntityCache
        mock_redis = AsyncMock()
        cache = RedisEntityCache(redis_client=mock_redis, namespace="testns")
        assert cache._make_key("thekey") == "testns:thekey"


# ---------------------------------------------------------------------------
# EntityCache abstract base
# ---------------------------------------------------------------------------

class TestEntityCacheAbstractR4:
    def test_get_namespace(self):
        from ii_agent.core.redis.cache import MemoryEntityCache
        cache = MemoryEntityCache(namespace="ns1")
        assert cache.get_namespace() == "ns1"

    def test_make_key_prefix(self):
        from ii_agent.core.redis.cache import MemoryEntityCache
        cache = MemoryEntityCache(namespace="myns")
        assert cache._make_key("foo") == "myns:foo"


# ---------------------------------------------------------------------------
# create_entity_cache factory
# ---------------------------------------------------------------------------

class TestCreateEntityCacheR4:
    def test_creates_memory_cache_when_no_redis(self):
        from ii_agent.core.redis.cache import create_entity_cache, MemoryEntityCache
        with patch("ii_agent.core.redis.client.redis_client", None):
            cache = create_entity_cache(namespace="test", ttl=60)
        assert isinstance(cache, MemoryEntityCache)

    def test_creates_redis_cache_when_redis_available(self):
        from ii_agent.core.redis.cache import create_entity_cache, RedisEntityCache
        mock_redis = MagicMock()
        with patch("ii_agent.core.redis.client.redis_client", mock_redis):
            cache = create_entity_cache(namespace="test", ttl=60)
        assert isinstance(cache, RedisEntityCache)
