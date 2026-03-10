"""Unit tests for realtime subscribers (r4).

Covers:
- subscriber.py (EventSubscriber base class)
- database_subscriber.py (DatabaseSubscriber)
- metrics_subscriber.py (MetricsSubscriber)
- socketio_subscriber.py (SocketIOSubscriber)
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.realtime.events.models import EventType, RealtimeEvent
from ii_agent.agent.agents.models import RunStatus

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    event_type: EventType = EventType.STATUS_UPDATE,
    session_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    content: dict | None = None,
) -> RealtimeEvent:
    return RealtimeEvent(
        session_id=session_id or uuid.uuid4(),
        run_id=run_id,
        type=event_type,
        content=content or {},
    )


def _make_db_cm_factory():
    """Return a callable that produces a fresh async CM each call."""
    @asynccontextmanager
    async def _cm():
        yield AsyncMock()
    return _cm


# Convenience alias used in patch(return_value=...) where the patched function
# itself is called. Each patch call provides a different side_effect.
def _fake_db_cm():
    """Single fresh async context manager (use side_effect for multi-call scenarios)."""
    @asynccontextmanager
    async def _cm():
        yield AsyncMock()
    return _cm()


# ---------------------------------------------------------------------------
# EventSubscriber.should_handle
# ---------------------------------------------------------------------------


class TestEventSubscriberShouldHandle:
    """Test EventSubscriber.should_handle logic without hitting DB."""

    def _make_subscriber(self):
        """Create a concrete EventSubscriber for testing."""
        from ii_agent.realtime.subscribers.subscriber import EventSubscriber

        class _Concrete(EventSubscriber):
            async def handle_event(self, event):
                pass

        return _Concrete()

    @pytest.mark.asyncio
    async def test_returns_true_when_no_run_id(self):
        sub = self._make_subscriber()
        event = _make_event(EventType.STATUS_UPDATE, run_id=None)
        result = await sub.should_handle(event)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_for_allowed_when_aborted_types_without_run_id(self):
        sub = self._make_subscriber()
        for et in [
            EventType.ERROR,
            EventType.PONG,
            EventType.STREAM_COMPLETE,
            EventType.SYSTEM,
        ]:
            event = _make_event(et, run_id=None)
            result = await sub.should_handle(event)
            assert result is True, f"Expected True for {et}"

    @pytest.mark.asyncio
    async def test_returns_true_for_allowed_types_even_with_run_id(self):
        sub = self._make_subscriber()
        run_id = uuid.uuid4()
        # For allowed_when_aborted types with run_id, still returns True
        event = _make_event(EventType.STREAM_COMPLETE, run_id=run_id)
        result = await sub.should_handle(event)
        assert result is True

    @pytest.mark.asyncio
    async def test_queries_db_when_run_id_present_and_not_allowed_type(self):
        sub = self._make_subscriber()
        run_id = uuid.uuid4()
        event = _make_event(EventType.TOOL_CALL, run_id=run_id)

        mock_task = MagicMock()
        mock_task.status = RunStatus.RUNNING
        mock_agent_run_service = MagicMock()
        mock_agent_run_service.get_task_by_id = AsyncMock(return_value=mock_task)

        with patch(
            "ii_agent.realtime.subscribers.subscriber.get_db_session_local",
            return_value=_fake_db_cm(),
        ), patch.object(sub, "_get_agent_run_service", return_value=mock_agent_run_service):
            result = await sub.should_handle(event)

        assert result is True  # Task is RUNNING

    @pytest.mark.asyncio
    async def test_returns_false_when_task_not_running(self):
        sub = self._make_subscriber()
        run_id = uuid.uuid4()
        event = _make_event(EventType.TOOL_CALL, run_id=run_id)

        mock_task = MagicMock()
        mock_task.status = RunStatus.COMPLETED
        mock_agent_run_service = MagicMock()
        mock_agent_run_service.get_task_by_id = AsyncMock(return_value=mock_task)

        with patch(
            "ii_agent.realtime.subscribers.subscriber.get_db_session_local",
            return_value=_fake_db_cm(),
        ), patch.object(sub, "_get_agent_run_service", return_value=mock_agent_run_service):
            result = await sub.should_handle(event)

        assert result is False

    @pytest.mark.asyncio
    async def test_raises_when_task_not_found(self):
        sub = self._make_subscriber()
        run_id = uuid.uuid4()
        event = _make_event(EventType.TOOL_CALL, run_id=run_id)

        mock_agent_run_service = MagicMock()
        mock_agent_run_service.get_task_by_id = AsyncMock(return_value=None)

        with patch(
            "ii_agent.realtime.subscribers.subscriber.get_db_session_local",
            return_value=_fake_db_cm(),
        ), patch.object(sub, "_get_agent_run_service", return_value=mock_agent_run_service):
            with pytest.raises(ValueError, match="Task run not found"):
                await sub.should_handle(event)


# ---------------------------------------------------------------------------
# EventType.is_allowed_when_aborted
# ---------------------------------------------------------------------------


class TestEventTypeIsAllowedWhenAborted:
    def test_error_is_allowed(self):
        assert EventType.is_allowed_when_aborted(EventType.ERROR) is True

    def test_system_is_allowed(self):
        assert EventType.is_allowed_when_aborted(EventType.SYSTEM) is True

    def test_pong_is_allowed(self):
        assert EventType.is_allowed_when_aborted(EventType.PONG) is True

    def test_stream_complete_is_allowed(self):
        assert EventType.is_allowed_when_aborted(EventType.STREAM_COMPLETE) is True

    def test_status_update_is_allowed(self):
        assert EventType.is_allowed_when_aborted(EventType.STATUS_UPDATE) is True

    def test_tool_call_not_allowed(self):
        assert EventType.is_allowed_when_aborted(EventType.TOOL_CALL) is False

    def test_tool_result_not_allowed(self):
        assert EventType.is_allowed_when_aborted(EventType.TOOL_RESULT) is False

    def test_agent_response_not_allowed(self):
        assert EventType.is_allowed_when_aborted(EventType.AGENT_RESPONSE) is False

    def test_processing_not_allowed(self):
        assert EventType.is_allowed_when_aborted(EventType.PROCESSING) is False


# ---------------------------------------------------------------------------
# MetricsSubscriber
# ---------------------------------------------------------------------------


class TestMetricsSubscriber:
    def _make_subscriber(self):
        from ii_agent.realtime.subscribers.metrics_subscriber import MetricsSubscriber

        return MetricsSubscriber()

    @pytest.mark.asyncio
    async def test_skips_event_when_no_session_id(self):
        sub = self._make_subscriber()
        event = RealtimeEvent(
            session_id=None,
            type=EventType.METRICS_UPDATE,
            content={"metrics": {}},
        )
        # Should return without error
        await sub.handle_event(event)

    @pytest.mark.asyncio
    async def test_handles_metrics_update_event(self):
        sub = self._make_subscriber()
        event = _make_event(EventType.METRICS_UPDATE, run_id=None)
        # should_handle returns True (no run_id), handle_event logs and returns
        await sub.handle_event(event)

    @pytest.mark.asyncio
    async def test_handles_tool_result_event(self):
        sub = self._make_subscriber()
        event = _make_event(EventType.TOOL_RESULT, run_id=None)
        await sub.handle_event(event)

    @pytest.mark.asyncio
    async def test_skips_non_metrics_non_tool_result(self):
        sub = self._make_subscriber()
        event = _make_event(EventType.AGENT_RESPONSE, run_id=None)
        # should_handle returns True (no run_id), but no action for this type
        await sub.handle_event(event)

    @pytest.mark.asyncio
    async def test_handle_tool_result_is_noop(self):
        sub = self._make_subscriber()
        event = _make_event(EventType.TOOL_RESULT, run_id=None, content={"tool_name": "bash"})
        # _handle_tool_result is a no-op per implementation
        result = await sub._handle_tool_result(event)
        assert result is None

    @pytest.mark.asyncio
    async def test_logs_metrics_update_without_raising(self):
        sub = self._make_subscriber()
        event = _make_event(
            EventType.METRICS_UPDATE,
            run_id=None,
            content={"metrics": {"input_tokens": 100, "output_tokens": 50}},
        )
        # Should not raise
        await sub.handle_event(event)

    @pytest.mark.asyncio
    async def test_returns_when_should_handle_false(self):
        sub = self._make_subscriber()
        run_id = uuid.uuid4()
        event = _make_event(EventType.TOOL_CALL, run_id=run_id)

        mock_task = MagicMock()
        mock_task.status = RunStatus.COMPLETED
        mock_agent_run_service = MagicMock()
        mock_agent_run_service.get_task_by_id = AsyncMock(return_value=mock_task)

        with patch(
            "ii_agent.realtime.subscribers.subscriber.get_db_session_local",
            return_value=_fake_db_cm(),
        ), patch.object(sub, "_get_agent_run_service", return_value=mock_agent_run_service):
            await sub.handle_event(event)  # Should return early


# ---------------------------------------------------------------------------
# DatabaseSubscriber
# ---------------------------------------------------------------------------


class TestDatabaseSubscriber:
    def _make_subscriber(self):
        from ii_agent.realtime.subscribers.database_subscriber import DatabaseSubscriber

        container = MagicMock()
        container.agent_run_service = MagicMock()
        container.agent_run_service.get_task_by_id = AsyncMock()
        container.file_service = MagicMock()
        container.file_service.write_file_from_url = AsyncMock()
        return DatabaseSubscriber(container=container)

    @pytest.mark.asyncio
    async def test_skips_user_message_events(self):
        sub = self._make_subscriber()
        event = _make_event(EventType.USER_MESSAGE, run_id=None)
        # Should not save to DB (USER_MESSAGE is skipped)
        with patch(
            "ii_agent.realtime.subscribers.database_subscriber.get_db_session_local",
            return_value=_fake_db_cm(),
        ):
            await sub.handle_event(event)

    @pytest.mark.asyncio
    async def test_skips_plan_generated_events(self):
        sub = self._make_subscriber()
        event = _make_event(EventType.PLAN_GENERATED, run_id=None)
        with patch(
            "ii_agent.realtime.subscribers.database_subscriber.get_db_session_local",
            return_value=_fake_db_cm(),
        ):
            await sub.handle_event(event)

    @pytest.mark.asyncio
    async def test_skips_milestone_update_events(self):
        sub = self._make_subscriber()
        event = _make_event(EventType.MILESTONE_UPDATE, run_id=None)
        with patch(
            "ii_agent.realtime.subscribers.database_subscriber.get_db_session_local",
            return_value=_fake_db_cm(),
        ):
            await sub.handle_event(event)

    @pytest.mark.asyncio
    async def test_skips_agent_thinking_delta_events(self):
        sub = self._make_subscriber()
        event = _make_event(EventType.AGENT_THINKING_DELTA, run_id=None)
        with patch(
            "ii_agent.realtime.subscribers.database_subscriber.get_db_session_local",
            return_value=_fake_db_cm(),
        ):
            await sub.handle_event(event)

    @pytest.mark.asyncio
    async def test_skips_agent_response_delta_events(self):
        sub = self._make_subscriber()
        event = _make_event(EventType.AGENT_RESPONSE_DELTA, run_id=None)
        with patch(
            "ii_agent.realtime.subscribers.database_subscriber.get_db_session_local",
            return_value=_fake_db_cm(),
        ):
            await sub.handle_event(event)

    @pytest.mark.asyncio
    async def test_skips_events_without_session_id(self):
        sub = self._make_subscriber()
        event = RealtimeEvent(
            session_id=None,
            type=EventType.TOOL_RESULT,
            content={"result": {}},
        )
        # No session_id: should skip
        with patch(
            "ii_agent.realtime.subscribers.database_subscriber.get_db_session_local",
            return_value=_fake_db_cm(),
        ):
            await sub.handle_event(event)

    @pytest.mark.asyncio
    async def test_saves_regular_event_to_db(self):
        sub = self._make_subscriber()
        event = _make_event(EventType.AGENT_RESPONSE, run_id=None)

        mock_repo = MagicMock()
        mock_repo.save = AsyncMock()

        with patch(
            "ii_agent.realtime.subscribers.database_subscriber.get_db_session_local",
            return_value=_fake_db_cm(),
        ), patch(
            "ii_agent.realtime.subscribers.database_subscriber.EventRepository",
            return_value=mock_repo,
        ):
            await sub.handle_event(event)

        mock_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_tool_result_with_file_url(self):
        sub = self._make_subscriber()
        session_id = uuid.uuid4()
        event = _make_event(
            EventType.TOOL_RESULT,
            session_id=session_id,
            run_id=None,
            content={
                "result": {
                    "type": "file_url",
                    "url": "https://example.com/img.png",
                    "name": "img.png",
                    "size": 1024,
                    "mime_type": "image/png",
                },
                "tool_name": "image_gen",
            },
        )

        mock_file_data = MagicMock()
        mock_file_data.id = "file-123"
        mock_file_data.storage_path = "/storage/img.png"
        sub._container.file_service.write_file_from_url = AsyncMock(return_value=mock_file_data)

        mock_repo = MagicMock()
        mock_repo.save = AsyncMock()

        # Use side_effect (not return_value) so each call creates a fresh CM
        db_factory = _make_db_cm_factory()
        with patch(
            "ii_agent.realtime.subscribers.database_subscriber.get_db_session_local",
            side_effect=db_factory,
        ), patch(
            "ii_agent.realtime.subscribers.database_subscriber.EventRepository",
            return_value=mock_repo,
        ):
            await sub.handle_event(event)

        # Verify file_id was added to event content
        assert event.content["result"]["file_id"] == "file-123"

    @pytest.mark.asyncio
    async def test_swallows_integrity_error_on_duplicate_save(self):
        from sqlalchemy.exc import IntegrityError

        sub = self._make_subscriber()
        event = _make_event(EventType.AGENT_RESPONSE, run_id=None)

        mock_repo = MagicMock()
        mock_repo.save = AsyncMock(
            side_effect=IntegrityError("duplicate", {}, Exception(""))
        )

        with patch(
            "ii_agent.realtime.subscribers.database_subscriber.get_db_session_local",
            return_value=_fake_db_cm(),
        ), patch(
            "ii_agent.realtime.subscribers.database_subscriber.EventRepository",
            return_value=mock_repo,
        ):
            # Should NOT raise – IntegrityError is swallowed
            await sub.handle_event(event)

    @pytest.mark.asyncio
    async def test_saves_tool_call_event(self):
        sub = self._make_subscriber()
        event = _make_event(EventType.TOOL_CALL, run_id=None, content={"tool_name": "bash"})

        mock_repo = MagicMock()
        mock_repo.save = AsyncMock()

        with patch(
            "ii_agent.realtime.subscribers.database_subscriber.get_db_session_local",
            return_value=_fake_db_cm(),
        ), patch(
            "ii_agent.realtime.subscribers.database_subscriber.EventRepository",
            return_value=mock_repo,
        ):
            await sub.handle_event(event)

        mock_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_result_non_file_url_saves_normally(self):
        sub = self._make_subscriber()
        event = _make_event(
            EventType.TOOL_RESULT,
            run_id=None,
            content={"result": {"output": "some text"}, "tool_name": "bash"},
        )

        mock_repo = MagicMock()
        mock_repo.save = AsyncMock()

        with patch(
            "ii_agent.realtime.subscribers.database_subscriber.get_db_session_local",
            return_value=_fake_db_cm(),
        ), patch(
            "ii_agent.realtime.subscribers.database_subscriber.EventRepository",
            return_value=mock_repo,
        ):
            await sub.handle_event(event)

        mock_repo.save.assert_called_once()


# ---------------------------------------------------------------------------
# SocketIOSubscriber
# ---------------------------------------------------------------------------


class FakeSio:
    def __init__(self):
        self.emitted: list = []
        self.manager = MagicMock()
        self.manager.get_participants = MagicMock(return_value=iter([]))

    async def emit(self, event_name, data, room=None, **kwargs):
        self.emitted.append((event_name, data, room))


class TestSocketIOSubscriber:
    def _make_subscriber(self, sio=None):
        from ii_agent.realtime.subscribers.socketio_subscriber import SocketIOSubscriber

        return SocketIOSubscriber(sio=sio or FakeSio())

    @pytest.mark.asyncio
    async def test_broadcasts_event_to_room(self):
        sio = FakeSio()
        sub = self._make_subscriber(sio=sio)
        session_id = uuid.uuid4()
        event = _make_event(EventType.AGENT_RESPONSE, session_id=session_id, run_id=None)

        await sub.handle_event(event)

        assert len(sio.emitted) == 1
        event_name, data, room = sio.emitted[0]
        assert event_name == "chat_event"
        assert room == str(session_id)
        assert data["type"] == EventType.AGENT_RESPONSE
        assert data["session_id"] == str(session_id)

    @pytest.mark.asyncio
    async def test_skips_event_when_no_session_id(self):
        sio = FakeSio()
        sub = self._make_subscriber(sio=sio)
        event = RealtimeEvent(
            session_id=None,
            type=EventType.AGENT_RESPONSE,
            content={},
        )
        await sub.handle_event(event)
        assert len(sio.emitted) == 0

    @pytest.mark.asyncio
    async def test_event_data_includes_run_id(self):
        sio = FakeSio()
        sub = self._make_subscriber(sio=sio)
        session_id = uuid.uuid4()
        run_id = uuid.uuid4()
        # TOOL_CALL + run_id triggers should_handle DB lookup; mock it
        event = _make_event(EventType.TOOL_CALL, session_id=session_id, run_id=run_id)

        mock_task = MagicMock()
        mock_task.status = RunStatus.RUNNING
        mock_svc = MagicMock()
        mock_svc.get_task_by_id = AsyncMock(return_value=mock_task)

        with patch(
            "ii_agent.realtime.subscribers.subscriber.get_db_session_local",
            side_effect=_make_db_cm_factory(),
        ), patch.object(sub, "_get_agent_run_service", return_value=mock_svc):
            await sub.handle_event(event)

        _, data, _ = sio.emitted[0]
        assert data["run_id"] == str(run_id)

    @pytest.mark.asyncio
    async def test_event_data_run_id_none_when_not_set(self):
        sio = FakeSio()
        sub = self._make_subscriber(sio=sio)
        session_id = uuid.uuid4()
        event = _make_event(EventType.AGENT_RESPONSE, session_id=session_id, run_id=None)

        await sub.handle_event(event)

        _, data, _ = sio.emitted[0]
        assert data["run_id"] is None

    @pytest.mark.asyncio
    async def test_event_content_includes_session_id(self):
        sio = FakeSio()
        sub = self._make_subscriber(sio=sio)
        session_id = uuid.uuid4()
        event = _make_event(
            EventType.STATUS_UPDATE,
            session_id=session_id,
            run_id=None,
            content={"message": "updating"},
        )
        await sub.handle_event(event)

        _, data, _ = sio.emitted[0]
        assert data["content"]["session_id"] == str(session_id)
        assert data["content"]["message"] == "updating"

    @pytest.mark.asyncio
    async def test_swallows_emit_exception(self):
        sio = FakeSio()
        sio.emit = AsyncMock(side_effect=Exception("emit failed"))
        sub = self._make_subscriber(sio=sio)
        session_id = uuid.uuid4()
        event = _make_event(EventType.AGENT_RESPONSE, session_id=session_id, run_id=None)
        # Should not propagate the exception
        await sub.handle_event(event)

    @pytest.mark.asyncio
    async def test_run_status_included_in_event_data(self):
        sio = FakeSio()
        sub = self._make_subscriber(sio=sio)
        session_id = uuid.uuid4()
        event = _make_event(EventType.STREAM_COMPLETE, session_id=session_id, run_id=None)
        event.run_status = "completed"

        await sub.handle_event(event)

        _, data, _ = sio.emitted[0]
        assert data["run_status"] == "completed"

    @pytest.mark.asyncio
    async def test_returns_early_when_should_handle_false(self):
        sio = FakeSio()
        sub = self._make_subscriber(sio=sio)
        session_id = uuid.uuid4()
        run_id = uuid.uuid4()
        event = _make_event(EventType.TOOL_CALL, session_id=session_id, run_id=run_id)

        mock_task = MagicMock()
        mock_task.status = RunStatus.ABORTED
        mock_agent_run_service = MagicMock()
        mock_agent_run_service.get_task_by_id = AsyncMock(return_value=mock_task)

        with patch(
            "ii_agent.realtime.subscribers.subscriber.get_db_session_local",
            return_value=_fake_db_cm(),
        ), patch.object(sub, "_get_agent_run_service", return_value=mock_agent_run_service):
            await sub.handle_event(event)

        # TOOL_CALL not allowed when aborted, so should not emit
        assert len(sio.emitted) == 0
