"""Unit tests for realtime event publishers (r4).

Covers:
- NoopEventPublisher
- SocketIOEventPublisher (publish via redis_manager and via sio)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.realtime.events.models import EventType, RealtimeEvent

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    event_type: EventType = EventType.STATUS_UPDATE,
    session_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    content: dict | None = None,
    run_status: str | None = None,
) -> RealtimeEvent:
    return RealtimeEvent(
        session_id=session_id or uuid.uuid4(),
        run_id=run_id,
        type=event_type,
        content=content or {},
        run_status=run_status,
    )


# ---------------------------------------------------------------------------
# NoopEventPublisher
# ---------------------------------------------------------------------------


class TestNoopEventPublisher:
    @pytest.mark.asyncio
    async def test_publish_does_nothing(self):
        from ii_agent.realtime.events.publisher import NoopEventPublisher

        pub = NoopEventPublisher()
        event = _make_event()
        result = await pub.publish(event)
        assert result is None

    @pytest.mark.asyncio
    async def test_publish_does_not_raise(self):
        from ii_agent.realtime.events.publisher import NoopEventPublisher

        pub = NoopEventPublisher()
        for et in EventType:
            event = _make_event(et)
            await pub.publish(event)  # Should never raise

    @pytest.mark.asyncio
    async def test_publish_multiple_events_without_side_effects(self):
        from ii_agent.realtime.events.publisher import NoopEventPublisher

        pub = NoopEventPublisher()
        for _ in range(5):
            await pub.publish(_make_event())


# ---------------------------------------------------------------------------
# SocketIOEventPublisher – no_session_id
# ---------------------------------------------------------------------------


class TestSocketIOEventPublisherNoSessionId:
    @pytest.mark.asyncio
    async def test_returns_early_when_no_session_id(self):
        from ii_agent.realtime.events.publisher import SocketIOEventPublisher

        mock_sio = AsyncMock()
        pub = SocketIOEventPublisher(sio=mock_sio)
        event = RealtimeEvent(
            session_id=None,
            type=EventType.AGENT_RESPONSE,
            content={},
        )
        await pub.publish(event)
        mock_sio.emit.assert_not_called()


# ---------------------------------------------------------------------------
# SocketIOEventPublisher – publish via Socket.IO server (no redis)
# ---------------------------------------------------------------------------


class TestSocketIOEventPublisherViaSio:
    @pytest.mark.asyncio
    async def test_emits_chat_event_to_session_room(self):
        from ii_agent.realtime.events.publisher import SocketIOEventPublisher

        mock_sio = MagicMock()
        mock_sio.emit = AsyncMock()
        pub = SocketIOEventPublisher(sio=mock_sio)

        session_id = uuid.uuid4()
        event = _make_event(EventType.AGENT_RESPONSE, session_id=session_id)
        await pub.publish(event)

        mock_sio.emit.assert_called_once()
        call_args = mock_sio.emit.call_args
        assert call_args[0][0] == "chat_event"
        assert call_args[1]["room"] == str(session_id)

    @pytest.mark.asyncio
    async def test_event_data_contains_type(self):
        from ii_agent.realtime.events.publisher import SocketIOEventPublisher

        mock_sio = MagicMock()
        mock_sio.emit = AsyncMock()
        pub = SocketIOEventPublisher(sio=mock_sio)

        session_id = uuid.uuid4()
        event = _make_event(EventType.TOOL_CALL, session_id=session_id)
        await pub.publish(event)

        event_data = mock_sio.emit.call_args[0][1]
        assert event_data["type"] == EventType.TOOL_CALL

    @pytest.mark.asyncio
    async def test_event_data_contains_session_id_string(self):
        from ii_agent.realtime.events.publisher import SocketIOEventPublisher

        mock_sio = MagicMock()
        mock_sio.emit = AsyncMock()
        pub = SocketIOEventPublisher(sio=mock_sio)

        session_id = uuid.uuid4()
        event = _make_event(EventType.STATUS_UPDATE, session_id=session_id)
        await pub.publish(event)

        event_data = mock_sio.emit.call_args[0][1]
        assert event_data["session_id"] == str(session_id)

    @pytest.mark.asyncio
    async def test_event_data_contains_run_id_when_set(self):
        from ii_agent.realtime.events.publisher import SocketIOEventPublisher

        mock_sio = MagicMock()
        mock_sio.emit = AsyncMock()
        pub = SocketIOEventPublisher(sio=mock_sio)

        session_id = uuid.uuid4()
        run_id = uuid.uuid4()
        event = _make_event(EventType.PROCESSING, session_id=session_id, run_id=run_id)
        await pub.publish(event)

        event_data = mock_sio.emit.call_args[0][1]
        assert event_data["run_id"] == str(run_id)

    @pytest.mark.asyncio
    async def test_event_data_run_id_none_when_not_set(self):
        from ii_agent.realtime.events.publisher import SocketIOEventPublisher

        mock_sio = MagicMock()
        mock_sio.emit = AsyncMock()
        pub = SocketIOEventPublisher(sio=mock_sio)

        session_id = uuid.uuid4()
        event = _make_event(EventType.STATUS_UPDATE, session_id=session_id, run_id=None)
        await pub.publish(event)

        event_data = mock_sio.emit.call_args[0][1]
        assert event_data["run_id"] is None

    @pytest.mark.asyncio
    async def test_event_data_run_status(self):
        from ii_agent.realtime.events.publisher import SocketIOEventPublisher

        mock_sio = MagicMock()
        mock_sio.emit = AsyncMock()
        pub = SocketIOEventPublisher(sio=mock_sio)

        session_id = uuid.uuid4()
        event = _make_event(EventType.STREAM_COMPLETE, session_id=session_id, run_status="done")
        await pub.publish(event)

        event_data = mock_sio.emit.call_args[0][1]
        assert event_data["run_status"] == "done"

    @pytest.mark.asyncio
    async def test_content_includes_session_id(self):
        from ii_agent.realtime.events.publisher import SocketIOEventPublisher

        mock_sio = MagicMock()
        mock_sio.emit = AsyncMock()
        pub = SocketIOEventPublisher(sio=mock_sio)

        session_id = uuid.uuid4()
        event = _make_event(
            EventType.AGENT_RESPONSE,
            session_id=session_id,
            content={"text": "hello"},
        )
        await pub.publish(event)

        event_data = mock_sio.emit.call_args[0][1]
        assert event_data["content"]["session_id"] == str(session_id)
        assert event_data["content"]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_swallows_sio_emit_exception(self):
        from ii_agent.realtime.events.publisher import SocketIOEventPublisher

        mock_sio = MagicMock()
        mock_sio.emit = AsyncMock(side_effect=Exception("emit failed"))
        pub = SocketIOEventPublisher(sio=mock_sio)

        session_id = uuid.uuid4()
        event = _make_event(EventType.STATUS_UPDATE, session_id=session_id)
        # Should not raise
        await pub.publish(event)

    @pytest.mark.asyncio
    async def test_uses_custom_namespace(self):
        from ii_agent.realtime.events.publisher import SocketIOEventPublisher

        mock_sio = MagicMock()
        mock_sio.emit = AsyncMock()
        pub = SocketIOEventPublisher(sio=mock_sio, namespace="/chat")

        session_id = uuid.uuid4()
        event = _make_event(EventType.AGENT_RESPONSE, session_id=session_id)
        await pub.publish(event)

        # namespace is stored but sio.emit call should still work
        mock_sio.emit.assert_called_once()


# ---------------------------------------------------------------------------
# SocketIOEventPublisher – publish via Redis manager
# ---------------------------------------------------------------------------


class TestSocketIOEventPublisherViaRedis:
    @pytest.mark.asyncio
    async def test_uses_redis_manager_when_available(self):
        from ii_agent.realtime.events.publisher import SocketIOEventPublisher

        mock_redis = MagicMock()
        mock_redis.emit = AsyncMock()
        pub = SocketIOEventPublisher(redis_manager=mock_redis)

        session_id = uuid.uuid4()
        event = _make_event(EventType.AGENT_RESPONSE, session_id=session_id)
        await pub.publish(event)

        mock_redis.emit.assert_called_once()
        call_kwargs = mock_redis.emit.call_args[1]
        assert call_kwargs["room"] == str(session_id)

    @pytest.mark.asyncio
    async def test_redis_emit_includes_correct_event_name(self):
        from ii_agent.realtime.events.publisher import SocketIOEventPublisher

        mock_redis = MagicMock()
        mock_redis.emit = AsyncMock()
        pub = SocketIOEventPublisher(redis_manager=mock_redis)

        session_id = uuid.uuid4()
        event = _make_event(EventType.TOOL_RESULT, session_id=session_id)
        await pub.publish(event)

        call_args = mock_redis.emit.call_args
        assert call_args[0][0] == "chat_event"

    @pytest.mark.asyncio
    async def test_falls_back_to_sio_when_redis_fails(self):
        from ii_agent.realtime.events.publisher import SocketIOEventPublisher

        mock_redis = MagicMock()
        mock_redis.emit = AsyncMock(side_effect=Exception("redis down"))

        mock_sio = MagicMock()
        mock_sio.emit = AsyncMock()

        pub = SocketIOEventPublisher(sio=mock_sio, redis_manager=mock_redis)

        session_id = uuid.uuid4()
        event = _make_event(EventType.AGENT_RESPONSE, session_id=session_id)
        await pub.publish(event)

        # Redis failed, so sio.emit should be called as fallback
        mock_sio.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_does_not_fall_back_to_sio_on_success(self):
        from ii_agent.realtime.events.publisher import SocketIOEventPublisher

        mock_redis = MagicMock()
        mock_redis.emit = AsyncMock()

        mock_sio = MagicMock()
        mock_sio.emit = AsyncMock()

        pub = SocketIOEventPublisher(sio=mock_sio, redis_manager=mock_redis)

        session_id = uuid.uuid4()
        event = _make_event(EventType.AGENT_RESPONSE, session_id=session_id)
        await pub.publish(event)

        # Redis succeeded – sio.emit should NOT be called
        mock_sio.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_namespace_passed_to_emit(self):
        from ii_agent.realtime.events.publisher import SocketIOEventPublisher

        mock_redis = MagicMock()
        mock_redis.emit = AsyncMock()
        pub = SocketIOEventPublisher(redis_manager=mock_redis, namespace="/custom")

        session_id = uuid.uuid4()
        event = _make_event(EventType.STATUS_UPDATE, session_id=session_id)
        await pub.publish(event)

        call_kwargs = mock_redis.emit.call_args[1]
        assert call_kwargs["namespace"] == "/custom"

    @pytest.mark.asyncio
    async def test_redis_both_missing_does_nothing(self):
        from ii_agent.realtime.events.publisher import SocketIOEventPublisher

        pub = SocketIOEventPublisher()  # No sio, no redis

        session_id = uuid.uuid4()
        event = _make_event(EventType.AGENT_RESPONSE, session_id=session_id)
        # Should not raise
        await pub.publish(event)


# ---------------------------------------------------------------------------
# EventPublisher Protocol compliance
# ---------------------------------------------------------------------------


class TestEventPublisherProtocol:
    def test_noop_has_publish_method(self):
        from ii_agent.realtime.events.publisher import NoopEventPublisher

        pub = NoopEventPublisher()
        assert callable(pub.publish)

    def test_socketio_has_publish_method(self):
        from ii_agent.realtime.events.publisher import SocketIOEventPublisher

        pub = SocketIOEventPublisher()
        assert callable(pub.publish)

    def test_all_exports_present(self):
        from ii_agent.realtime.events import publisher

        for name in ["EventPublisher", "NoopEventPublisher", "SocketIOEventPublisher"]:
            assert hasattr(publisher, name), f"Missing export: {name}"
