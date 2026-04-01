"""Tests for AsyncIOPubSub event-driven core with group-based routing."""

from __future__ import annotations

import asyncio
import uuid

import pytest

pytest.skip("Tested module was removed during refactoring", allow_module_level=True)

from ii_agent.realtime.events.app_events import (
    AgentEvent,
    ApplicationEvent,
    EventGroup,
    EventType,
    SystemEvent,
    UserEvent,
    is_allowed_when_aborted,
)
from ii_agent.realtime.events.run_lifecycle import RunLifecycle
from ii_agent.core.pubsub import AsyncIOPubSub

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL = "*"


def _make_event(
    group: str = EventGroup.SYSTEM,
    name: str = EventType.STATUS_UPDATE,
    session_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
) -> ApplicationEvent:
    return ApplicationEvent(
        group=group,
        name=name,
        session_id=session_id or uuid.uuid4(),
        run_id=run_id,
        content={"message": "test"},
    )


def _make_agent_event(
    group: str = EventGroup.AGENT_RUN,
    name: str = EventType.RUN_STARTED,
) -> AgentEvent:
    return AgentEvent(
        group=group,
        name=name,
        session_id=uuid.uuid4(),
        content={"message": "processing"},
        model="claude-3-5-sonnet",
        agent_name="test_agent",
    )


class _Collector:
    """Collects events for assertions."""

    def __init__(self) -> None:
        self.events: list[ApplicationEvent] = []

    async def __call__(self, event: ApplicationEvent) -> None:
        self.events.append(event)


class _ErrorHandler:
    """Handler that always raises."""

    async def __call__(self, event: ApplicationEvent) -> None:
        raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# ApplicationEvent model tests
# ---------------------------------------------------------------------------


class TestApplicationEvent:
    def test_creates_with_group_and_name(self):
        event = _make_event()
        assert event.group == EventGroup.SYSTEM
        assert event.name == EventType.STATUS_UPDATE
        assert event.content == {"message": "test"}
        assert event.id is not None
        assert event.timestamp > 0

    def test_agent_event_has_agent_fields(self):
        event = _make_agent_event()
        assert event.model == "claude-3-5-sonnet"
        assert event.agent_name == "test_agent"
        assert isinstance(event, ApplicationEvent)

    def test_user_event(self):
        event = UserEvent(
            group=EventGroup.USER,
            name=EventType.USER_MESSAGE,
            content={"text": "hello"},
            user_id="user-123",
        )
        assert event.user_id == "user-123"
        assert isinstance(event, ApplicationEvent)

    def test_system_event(self):
        event = SystemEvent(
            group=EventGroup.SYSTEM,
            name=EventType.PONG,
            content={},
        )
        assert isinstance(event, ApplicationEvent)


class TestIsAllowedWhenAborted:
    def test_system_error_is_allowed(self):
        event = _make_event(group=EventGroup.SYSTEM, name=EventType.ERROR)
        assert is_allowed_when_aborted(event) is True

    def test_system_pong_is_allowed(self):
        event = _make_event(group=EventGroup.SYSTEM, name=EventType.PONG)
        assert is_allowed_when_aborted(event) is True

    def test_run_completed_is_allowed(self):
        event = _make_event(group=EventGroup.AGENT_RUN, name=EventType.RUN_COMPLETED)
        assert is_allowed_when_aborted(event) is True

    def test_run_cancelled_is_allowed(self):
        event = _make_event(group=EventGroup.AGENT_RUN, name=EventType.RUN_CANCELLED)
        assert is_allowed_when_aborted(event) is True

    def test_tool_call_not_allowed(self):
        event = _make_event(group=EventGroup.AGENT_TOOL, name=EventType.TOOL_CALL_STARTED)
        assert is_allowed_when_aborted(event) is False

    def test_run_content_not_allowed(self):
        event = _make_event(group=EventGroup.AGENT_RUN, name=EventType.RUN_CONTENT)
        assert is_allowed_when_aborted(event) is False


# ---------------------------------------------------------------------------
# RunLifecycle tests
# ---------------------------------------------------------------------------


class TestRunLifecycle:
    @pytest.mark.asyncio
    async def test_register_and_unregister(self):
        lc = RunLifecycle()
        await lc.register("run-1")
        assert "run-1" in lc.active_run_ids()

        await lc.unregister("run-1")
        assert "run-1" not in lc.active_run_ids()

    @pytest.mark.asyncio
    async def test_wait_all_done_returns_empty_when_no_runs(self):
        lc = RunLifecycle()
        result = await lc.wait_all_done(timeout=1.0)
        assert result == []

    def test_set_and_check_status(self):
        from ii_agent.agents.runs.models import RunStatus

        lc = RunLifecycle()
        lc.set_status("run-1", RunStatus.RUNNING)
        assert lc.is_active("run-1") is True

        lc.set_status("run-1", RunStatus.COMPLETED)
        assert lc.is_active("run-1") is False

    def test_is_active_returns_none_on_cache_miss(self):
        lc = RunLifecycle()
        assert lc.is_active("unknown-run") is None


# ---------------------------------------------------------------------------
# AsyncIOPubSub event routing tests
# ---------------------------------------------------------------------------


class TestAsyncIOPubSubEventRouting:
    @pytest.mark.asyncio
    async def test_wildcard_receives_all_events(self):
        pubsub = AsyncIOPubSub()
        collector = _Collector()
        pubsub.subscribe(_ALL, collector)
        await pubsub.start()

        await pubsub.publish(EventGroup.SYSTEM, _make_event())
        await pubsub.publish(
            EventGroup.AGENT_TOOL,
            _make_event(
                group=EventGroup.AGENT_TOOL,
                name=EventType.TOOL_CALL_STARTED,
            ),
        )
        await asyncio.sleep(0.05)

        assert len(collector.events) == 2
        await pubsub.stop()

    @pytest.mark.asyncio
    async def test_group_routing_filters_events(self):
        pubsub = AsyncIOPubSub()
        system_col = _Collector()
        tool_col = _Collector()
        all_col = _Collector()

        pubsub.subscribe(EventGroup.SYSTEM, system_col)
        pubsub.subscribe(EventGroup.AGENT_TOOL, tool_col)
        pubsub.subscribe(_ALL, all_col)
        await pubsub.start()

        await pubsub.publish(EventGroup.SYSTEM, _make_event(name=EventType.PONG))
        await pubsub.publish(
            EventGroup.AGENT_TOOL,
            _make_event(
                group=EventGroup.AGENT_TOOL,
                name=EventType.TOOL_CALL_STARTED,
            ),
        )
        await asyncio.sleep(0.05)

        assert len(system_col.events) == 1
        assert system_col.events[0].name == EventType.PONG

        assert len(tool_col.events) == 1
        assert tool_col.events[0].name == EventType.TOOL_CALL_STARTED

        # Wildcard gets both
        assert len(all_col.events) == 2
        await pubsub.stop()

    @pytest.mark.asyncio
    async def test_error_in_handler_does_not_crash(self):
        pubsub = AsyncIOPubSub()
        error_handler = _ErrorHandler()
        collector = _Collector()

        pubsub.subscribe(_ALL, error_handler)
        pubsub.subscribe(_ALL, collector)
        await pubsub.start()

        await pubsub.publish(EventGroup.SYSTEM, _make_event())
        await asyncio.sleep(0.05)

        assert len(collector.events) == 1
        await pubsub.stop()

    @pytest.mark.asyncio
    async def test_publish_before_start_is_noop(self):
        pubsub = AsyncIOPubSub()
        collector = _Collector()
        pubsub.subscribe(_ALL, collector)

        # Publish before start — no queues exist, silently dropped
        await pubsub.publish(EventGroup.SYSTEM, _make_event())
        await asyncio.sleep(0.05)
        assert len(collector.events) == 0

    @pytest.mark.asyncio
    async def test_stop_cancels_dispatchers(self):
        pubsub = AsyncIOPubSub()
        collector = _Collector()
        pubsub.subscribe(_ALL, collector)
        await pubsub.start()

        await pubsub.stop()

        # After stop, queues are cleared — publish is noop
        await pubsub.publish(EventGroup.SYSTEM, _make_event())
        await asyncio.sleep(0.05)
        assert len(collector.events) == 0
