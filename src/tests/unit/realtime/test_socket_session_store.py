"""Unit tests for ii_agent.realtime.session_store."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.skip("Tested module was removed during refactoring", allow_module_level=True)

from ii_agent.realtime.session_store import (
    MemorySessionStore,
    RedisSessionStore,
    SessionStore,
    create_session_store,
)


# ---------------------------------------------------------------------------
# RedisSessionStore
# ---------------------------------------------------------------------------


class TestRedisSessionStoreInit:
    def test_default_prefix(self):
        with patch("ii_agent.realtime.session_store.redis_client", MagicMock()):
            store = RedisSessionStore()
        assert store.redis_key_prefix == "session_sids:"

    def test_custom_prefix(self):
        with patch("ii_agent.realtime.session_store.redis_client", MagicMock()):
            store = RedisSessionStore(redis_key_prefix="custom:")
        assert store.redis_key_prefix == "custom:"


class TestRedisSessionStoreGetRedisKey:
    def test_key_format(self):
        with patch("ii_agent.realtime.session_store.redis_client", MagicMock()):
            store = RedisSessionStore()
        key = store._get_redis_key("sess-abc")
        assert key == "session_sids:sess-abc"

    def test_key_with_custom_prefix(self):
        with patch("ii_agent.realtime.session_store.redis_client", MagicMock()):
            store = RedisSessionStore(redis_key_prefix="sids:")
        key = store._get_redis_key("xyz")
        assert key == "sids:xyz"


class TestRedisSessionStoreAddSid:
    @pytest.mark.asyncio
    async def test_calls_sadd_and_expire(self):
        mock_redis = AsyncMock()
        mock_redis.sadd = AsyncMock()
        mock_redis.expire = AsyncMock()

        with patch("ii_agent.realtime.session_store.redis_client", mock_redis):
            store = RedisSessionStore()
            await store.add_sid_to_session("sess1", "sid1")

        mock_redis.sadd.assert_awaited_once()
        mock_redis.expire.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_raise_on_redis_error(self):
        mock_redis = AsyncMock()
        mock_redis.sadd = AsyncMock(side_effect=Exception("redis down"))

        with patch("ii_agent.realtime.session_store.redis_client", mock_redis):
            store = RedisSessionStore()
            await store.add_sid_to_session("sess1", "sid1")  # Should not raise


class TestRedisSessionStoreRemoveSid:
    @pytest.mark.asyncio
    async def test_cleans_up_empty_key_after_remove(self):
        mock_redis = AsyncMock()
        mock_redis.srem = AsyncMock()
        mock_redis.scard = AsyncMock(return_value=0)
        mock_redis.delete = AsyncMock()
        mock_redis.expire = AsyncMock()

        with patch("ii_agent.realtime.session_store.redis_client", mock_redis):
            store = RedisSessionStore()
            await store.remove_sid_from_session("sess1", "sid1")

        mock_redis.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_refreshes_ttl_when_sids_remain(self):
        mock_redis = AsyncMock()
        mock_redis.srem = AsyncMock()
        mock_redis.scard = AsyncMock(return_value=2)
        mock_redis.expire = AsyncMock()

        with patch("ii_agent.realtime.session_store.redis_client", mock_redis):
            store = RedisSessionStore()
            await store.remove_sid_from_session("sess1", "sid1")

        mock_redis.expire.assert_awaited()

    @pytest.mark.asyncio
    async def test_does_not_raise_on_redis_error(self):
        mock_redis = AsyncMock()
        mock_redis.srem = AsyncMock(side_effect=Exception("redis down"))

        with patch("ii_agent.realtime.session_store.redis_client", mock_redis):
            store = RedisSessionStore()
            await store.remove_sid_from_session("sess1", "sid1")


class TestRedisSessionStoreGetSessionSids:
    @pytest.mark.asyncio
    async def test_returns_decoded_sids(self):
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value={b"sid1", b"sid2"})

        with patch("ii_agent.realtime.session_store.redis_client", mock_redis):
            store = RedisSessionStore()
            result = await store.get_session_sids("sess1")

        assert "sid1" in result
        assert "sid2" in result

    @pytest.mark.asyncio
    async def test_returns_empty_set_on_redis_error(self):
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(side_effect=Exception("error"))

        with patch("ii_agent.realtime.session_store.redis_client", mock_redis):
            store = RedisSessionStore()
            result = await store.get_session_sids("sess1")

        assert result == set()

    @pytest.mark.asyncio
    async def test_handles_string_sids_without_decoding(self):
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value={"sid1", "sid2"})

        with patch("ii_agent.realtime.session_store.redis_client", mock_redis):
            store = RedisSessionStore()
            result = await store.get_session_sids("sess1")

        assert "sid1" in result


class TestRedisSessionStoreIsSessionEmpty:
    @pytest.mark.asyncio
    async def test_returns_true_when_key_not_exists(self):
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=0)

        with patch("ii_agent.realtime.session_store.redis_client", mock_redis):
            store = RedisSessionStore()
            result = await store.is_session_empty("sess1")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_sids_exist(self):
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=1)
        mock_redis.scard = AsyncMock(return_value=3)

        with patch("ii_agent.realtime.session_store.redis_client", mock_redis):
            store = RedisSessionStore()
            result = await store.is_session_empty("sess1")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_on_redis_error(self):
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(side_effect=Exception("redis down"))

        with patch("ii_agent.realtime.session_store.redis_client", mock_redis):
            store = RedisSessionStore()
            result = await store.is_session_empty("sess1")

        assert result is True


class TestRedisSessionStoreGetAllSessionSids:
    @pytest.mark.asyncio
    async def test_returns_dict_with_all_sessions(self):
        mock_redis = AsyncMock()
        mock_redis.keys = AsyncMock(return_value=[b"session_sids:sess1", b"session_sids:sess2"])
        mock_redis.smembers = AsyncMock(return_value={b"sid-a"})

        with patch("ii_agent.realtime.session_store.redis_client", mock_redis):
            store = RedisSessionStore()
            result = await store.get_all_session_sids()

        assert "sess1" in result
        assert "sess2" in result

    @pytest.mark.asyncio
    async def test_returns_empty_dict_on_redis_error(self):
        mock_redis = AsyncMock()
        mock_redis.keys = AsyncMock(side_effect=Exception("error"))

        with patch("ii_agent.realtime.session_store.redis_client", mock_redis):
            store = RedisSessionStore()
            result = await store.get_all_session_sids()

        assert result == {}


# ---------------------------------------------------------------------------
# MemorySessionStore
# ---------------------------------------------------------------------------


class TestMemorySessionStoreInit:
    def test_default_ttl(self):
        store = MemorySessionStore()
        assert store.ttl_seconds == 3600

    def test_custom_ttl(self):
        store = MemorySessionStore(ttl_seconds=60)
        assert store.ttl_seconds == 60

    def test_initially_empty(self):
        store = MemorySessionStore()
        assert store._sessions == {}


class TestMemorySessionStoreAddSid:
    @pytest.mark.asyncio
    async def test_adds_sid_to_new_session(self):
        store = MemorySessionStore(ttl_seconds=9999)
        await store.add_sid_to_session("sess1", "sid1")
        sids = await store.get_session_sids("sess1")
        assert "sid1" in sids

    @pytest.mark.asyncio
    async def test_adds_multiple_sids_to_same_session(self):
        store = MemorySessionStore(ttl_seconds=9999)
        await store.add_sid_to_session("sess1", "sid1")
        await store.add_sid_to_session("sess1", "sid2")
        sids = await store.get_session_sids("sess1")
        assert {"sid1", "sid2"} <= sids

    @pytest.mark.asyncio
    async def test_creates_ttl_task(self):
        store = MemorySessionStore(ttl_seconds=9999)
        await store.add_sid_to_session("sess1", "sid1")
        assert "sess1" in store._ttl_tasks
        store._ttl_tasks["sess1"].cancel()


class TestMemorySessionStoreRemoveSid:
    @pytest.mark.asyncio
    async def test_removes_sid_from_session(self):
        store = MemorySessionStore(ttl_seconds=9999)
        await store.add_sid_to_session("sess1", "sid1")
        await store.remove_sid_from_session("sess1", "sid1")
        sids = await store.get_session_sids("sess1")
        assert "sid1" not in sids

    @pytest.mark.asyncio
    async def test_cleans_up_empty_session(self):
        store = MemorySessionStore(ttl_seconds=9999)
        await store.add_sid_to_session("sess1", "sid1")
        await store.remove_sid_from_session("sess1", "sid1")
        assert "sess1" not in store._sessions

    @pytest.mark.asyncio
    async def test_cancels_ttl_task_on_cleanup(self):
        store = MemorySessionStore(ttl_seconds=9999)
        await store.add_sid_to_session("sess1", "sid1")
        await store.remove_sid_from_session("sess1", "sid1")
        assert "sess1" not in store._ttl_tasks

    @pytest.mark.asyncio
    async def test_no_error_when_sid_not_in_session(self):
        store = MemorySessionStore(ttl_seconds=9999)
        await store.add_sid_to_session("sess1", "sid1")
        await store.remove_sid_from_session("sess1", "nonexistent")
        sids = await store.get_session_sids("sess1")
        assert "sid1" in sids

    @pytest.mark.asyncio
    async def test_no_error_when_session_not_present(self):
        store = MemorySessionStore(ttl_seconds=9999)
        await store.remove_sid_from_session("missing-sess", "sid1")


class TestMemorySessionStoreGetSessionSids:
    @pytest.mark.asyncio
    async def test_returns_empty_set_for_unknown_session(self):
        store = MemorySessionStore()
        result = await store.get_session_sids("unknown")
        assert result == set()

    @pytest.mark.asyncio
    async def test_returns_copy_not_reference(self):
        store = MemorySessionStore(ttl_seconds=9999)
        await store.add_sid_to_session("sess1", "sid1")
        result = await store.get_session_sids("sess1")
        result.add("external-sid")
        # Original should be unaffected
        original = await store.get_session_sids("sess1")
        assert "external-sid" not in original


class TestMemorySessionStoreIsSessionEmpty:
    @pytest.mark.asyncio
    async def test_returns_true_for_empty_string_uuid(self):
        store = MemorySessionStore()
        result = await store.is_session_empty("")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_for_nonexistent_session(self):
        store = MemorySessionStore()
        result = await store.is_session_empty("nonexistent")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_session_has_sids(self):
        store = MemorySessionStore(ttl_seconds=9999)
        await store.add_sid_to_session("sess1", "sid1")
        result = await store.is_session_empty("sess1")
        assert result is False


class TestMemorySessionStoreGetAllSessionSids:
    @pytest.mark.asyncio
    async def test_returns_all_sessions(self):
        store = MemorySessionStore(ttl_seconds=9999)
        await store.add_sid_to_session("sess1", "sid1")
        await store.add_sid_to_session("sess2", "sid2")
        result = await store.get_all_session_sids()
        assert "sess1" in result
        assert "sess2" in result

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_sessions(self):
        store = MemorySessionStore()
        result = await store.get_all_session_sids()
        assert result == {}


# ---------------------------------------------------------------------------
# create_session_store factory
# ---------------------------------------------------------------------------


class TestCreateSessionStore:
    def test_returns_redis_store_when_session_enabled(self):
        mock_settings = MagicMock()
        mock_settings.redis.session_enabled = True
        with (
            patch(
                "ii_agent.realtime.session_store.get_settings",
                return_value=mock_settings,
            ),
            patch("ii_agent.realtime.session_store.redis_client", MagicMock()),
        ):
            store = create_session_store()
        assert isinstance(store, RedisSessionStore)

    def test_returns_memory_store_when_session_disabled(self):
        mock_settings = MagicMock()
        mock_settings.redis.session_enabled = False
        with patch(
            "ii_agent.realtime.session_store.get_settings",
            return_value=mock_settings,
        ):
            store = create_session_store()
        assert isinstance(store, MemorySessionStore)
