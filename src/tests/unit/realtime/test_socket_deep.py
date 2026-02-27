"""Deep unit tests for realtime socket session_store covering all branches."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.realtime.socket.session_store import (
    MemorySessionStore,
    RedisSessionStore,
    SessionStore,
)


# ---------------------------------------------------------------------------
# MemorySessionStore
# ---------------------------------------------------------------------------


class TestMemorySessionStore:
    @pytest.mark.asyncio
    async def test_add_sid_creates_session_entry(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("session-1", "sid-a")
        sids = await store.get_session_sids("session-1")
        assert "sid-a" in sids

    @pytest.mark.asyncio
    async def test_add_multiple_sids_to_same_session(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("session-1", "sid-a")
        await store.add_sid_to_session("session-1", "sid-b")
        sids = await store.get_session_sids("session-1")
        assert "sid-a" in sids
        assert "sid-b" in sids

    @pytest.mark.asyncio
    async def test_remove_sid_removes_from_session(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("session-1", "sid-a")
        await store.add_sid_to_session("session-1", "sid-b")
        await store.remove_sid_from_session("session-1", "sid-a")
        sids = await store.get_session_sids("session-1")
        assert "sid-a" not in sids
        assert "sid-b" in sids

    @pytest.mark.asyncio
    async def test_remove_sid_cleans_up_empty_session(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("session-1", "sid-a")
        await store.remove_sid_from_session("session-1", "sid-a")
        # Session should be cleaned up
        sids = await store.get_session_sids("session-1")
        assert sids == set()
        assert "session-1" not in store._sessions

    @pytest.mark.asyncio
    async def test_remove_sid_from_nonexistent_session(self):
        store = MemorySessionStore()
        # Should not raise
        await store.remove_sid_from_session("no-session", "sid-x")

    @pytest.mark.asyncio
    async def test_get_session_sids_returns_empty_for_unknown(self):
        store = MemorySessionStore()
        sids = await store.get_session_sids("no-session")
        assert sids == set()

    @pytest.mark.asyncio
    async def test_get_all_session_sids(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("s-1", "sid-a")
        await store.add_sid_to_session("s-2", "sid-b")
        all_sessions = await store.get_all_session_sids()
        assert "s-1" in all_sessions
        assert "s-2" in all_sessions
        assert "sid-a" in all_sessions["s-1"]

    @pytest.mark.asyncio
    async def test_is_session_empty_true_when_no_sids(self):
        store = MemorySessionStore()
        result = await store.is_session_empty("no-session")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_session_empty_false_when_has_sids(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("s-1", "sid-a")
        result = await store.is_session_empty("s-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_session_empty_true_after_all_removed(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("s-1", "sid-a")
        await store.remove_sid_from_session("s-1", "sid-a")
        result = await store.is_session_empty("s-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_ttl_task_cancelled_on_re_add(self):
        store = MemorySessionStore(ttl_seconds=60)
        await store.add_sid_to_session("s-1", "sid-a")
        first_task = store._ttl_tasks.get("s-1")
        # Add again - should cancel the old task
        await store.add_sid_to_session("s-1", "sid-b")
        second_task = store._ttl_tasks.get("s-1")
        assert second_task is not first_task

    @pytest.mark.asyncio
    async def test_ttl_task_cancelled_on_remove_when_remaining(self):
        store = MemorySessionStore(ttl_seconds=60)
        await store.add_sid_to_session("s-1", "sid-a")
        await store.add_sid_to_session("s-1", "sid-b")
        await store.remove_sid_from_session("s-1", "sid-a")
        # Should have refreshed TTL task
        assert "s-1" in store._ttl_tasks

    @pytest.mark.asyncio
    async def test_get_session_sids_returns_copy_not_reference(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("s-1", "sid-a")
        sids = await store.get_session_sids("s-1")
        sids.add("sid-external")
        original_sids = await store.get_session_sids("s-1")
        assert "sid-external" not in original_sids


# ---------------------------------------------------------------------------
# RedisSessionStore
# ---------------------------------------------------------------------------


class TestRedisSessionStore:
    def _make_store(self) -> tuple[RedisSessionStore, AsyncMock]:
        store = RedisSessionStore(redis_key_prefix="test:")
        mock_redis = AsyncMock()
        store.redis_client = mock_redis
        return store, mock_redis

    @pytest.mark.asyncio
    async def test_get_redis_key_format(self):
        store = RedisSessionStore(redis_key_prefix="session_sids:")
        key = store._get_redis_key("session-abc")
        assert key == "session_sids:session-abc"

    @pytest.mark.asyncio
    async def test_add_sid_calls_sadd_and_expire(self):
        store, redis = self._make_store()
        redis.sadd = AsyncMock()
        redis.expire = AsyncMock()
        await store.add_sid_to_session("s-1", "sid-a")
        redis.sadd.assert_called_once_with("test:s-1", "sid-a")
        redis.expire.assert_called_once_with("test:s-1", 3600)

    @pytest.mark.asyncio
    async def test_add_sid_handles_redis_error(self):
        store, redis = self._make_store()
        redis.sadd = AsyncMock(side_effect=ConnectionError("Redis down"))
        # Should not raise
        await store.add_sid_to_session("s-1", "sid-a")

    @pytest.mark.asyncio
    async def test_remove_sid_calls_srem(self):
        store, redis = self._make_store()
        redis.srem = AsyncMock()
        redis.scard = AsyncMock(return_value=0)
        redis.delete = AsyncMock()
        await store.remove_sid_from_session("s-1", "sid-a")
        redis.srem.assert_called_once_with("test:s-1", "sid-a")

    @pytest.mark.asyncio
    async def test_remove_sid_deletes_key_when_empty(self):
        store, redis = self._make_store()
        redis.srem = AsyncMock()
        redis.scard = AsyncMock(return_value=0)
        redis.delete = AsyncMock()
        await store.remove_sid_from_session("s-1", "sid-a")
        redis.delete.assert_called_once_with("test:s-1")

    @pytest.mark.asyncio
    async def test_remove_sid_refreshes_ttl_when_has_remaining(self):
        store, redis = self._make_store()
        redis.srem = AsyncMock()
        redis.scard = AsyncMock(return_value=2)
        redis.expire = AsyncMock()
        await store.remove_sid_from_session("s-1", "sid-a")
        redis.expire.assert_called_once_with("test:s-1", 3600)

    @pytest.mark.asyncio
    async def test_remove_sid_handles_redis_error(self):
        store, redis = self._make_store()
        redis.srem = AsyncMock(side_effect=ConnectionError("Redis down"))
        # Should not raise
        await store.remove_sid_from_session("s-1", "sid-a")

    @pytest.mark.asyncio
    async def test_get_session_sids_returns_decoded_set(self):
        store, redis = self._make_store()
        redis.smembers = AsyncMock(return_value={b"sid-a", b"sid-b"})
        sids = await store.get_session_sids("s-1")
        assert "sid-a" in sids
        assert "sid-b" in sids

    @pytest.mark.asyncio
    async def test_get_session_sids_handles_string_members(self):
        store, redis = self._make_store()
        redis.smembers = AsyncMock(return_value={"sid-a", "sid-b"})
        sids = await store.get_session_sids("s-1")
        assert "sid-a" in sids

    @pytest.mark.asyncio
    async def test_get_session_sids_returns_empty_on_error(self):
        store, redis = self._make_store()
        redis.smembers = AsyncMock(side_effect=ConnectionError("Redis down"))
        sids = await store.get_session_sids("s-1")
        assert sids == set()

    @pytest.mark.asyncio
    async def test_get_all_session_sids_scans_keys(self):
        store, redis = self._make_store()
        redis.keys = AsyncMock(return_value=[b"test:s-1", b"test:s-2"])
        redis.smembers = AsyncMock(return_value={b"sid-a"})
        result = await store.get_all_session_sids()
        assert "s-1" in result
        assert "s-2" in result

    @pytest.mark.asyncio
    async def test_get_all_session_sids_returns_empty_on_error(self):
        store, redis = self._make_store()
        redis.keys = AsyncMock(side_effect=ConnectionError("Redis down"))
        result = await store.get_all_session_sids()
        assert result == {}

    @pytest.mark.asyncio
    async def test_is_session_empty_true_when_key_not_exists(self):
        store, redis = self._make_store()
        redis.exists = AsyncMock(return_value=0)
        result = await store.is_session_empty("s-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_session_empty_false_when_has_sids(self):
        store, redis = self._make_store()
        redis.exists = AsyncMock(return_value=1)
        redis.scard = AsyncMock(return_value=3)
        result = await store.is_session_empty("s-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_session_empty_true_when_count_zero(self):
        store, redis = self._make_store()
        redis.exists = AsyncMock(return_value=1)
        redis.scard = AsyncMock(return_value=0)
        result = await store.is_session_empty("s-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_session_empty_returns_true_on_error(self):
        store, redis = self._make_store()
        redis.exists = AsyncMock(side_effect=ConnectionError("Redis down"))
        result = await store.is_session_empty("s-1")
        assert result is True  # Assume empty on error
