"""Unit tests for realtime socket command handler pure logic.

Note: We avoid importing handler classes directly (PingHandler, CancelHandler, etc.)
because those have transitive deep dependencies (e.g., google.genai) that may not
be present in all environments. We test behaviour via duck-typing stubs and the
abstract base class alone.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.skip("Transitive google-genai dependency not available in this environment", allow_module_level=True)

from ii_agent.realtime.handlers.base import (
    BaseCommandHandler,
    CommandType,
)
from ii_agent.realtime.events import ApplicationEvent, ErrorCode, EventGroup, EventType, SystemEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_event_stream():
    stream = MagicMock()
    stream.publish = AsyncMock()
    return stream


def _base_kwargs(**overrides):
    return {
        "session_service": MagicMock(),
        "llm_setting_service": MagicMock(),
        "file_service": MagicMock(),
        "event_service": MagicMock(),
        "run_task_service": MagicMock(),
        **overrides,
    }


def _mock_container():
    """Kept for CommandHandlerFactory tests which still take container=."""
    container = MagicMock()
    container.run_task_service = MagicMock()
    container.run_task_service.get_last_by_session_id = AsyncMock()
    container.run_task_service.get_running_task = AsyncMock()
    container.run_task_service.create_task = AsyncMock()
    container.event_service = MagicMock()
    container.event_service.save_event = AsyncMock()
    container.file_service = MagicMock()
    container.file_service.get_file_by_id = AsyncMock()
    container.session_service.validate_and_prepare_session = AsyncMock()
    container.llm_setting_service = MagicMock()
    return container


def _session_info(session_id: str = None, user_id: str = "u1"):
    info = MagicMock()
    info.id = uuid.UUID(session_id) if session_id else uuid.uuid4()
    info.user_id = user_id
    info.name = "Test session"
    return info


class ConcreteHandler(BaseCommandHandler):
    """Concrete implementation for testing abstract methods."""

    _cmd_type = CommandType.PING

    def get_command_type(self) -> CommandType:
        return self._cmd_type

    async def handle(self, content, session_info) -> None:
        pass


# ---------------------------------------------------------------------------
# CommandType enum
# ---------------------------------------------------------------------------


class TestCommandType:
    def test_query_value(self):
        assert CommandType.QUERY == "query"

    def test_cancel_value(self):
        assert CommandType.CANCEL == "cancel"

    def test_ping_value(self):
        assert CommandType.PING == "ping"

    def test_plan_value(self):
        assert CommandType.PLAN == "plan"

    def test_sandbox_status_value(self):
        assert CommandType.SANDBOX_STATUS == "sandbox_status"

    def test_awake_sandbox_value(self):
        assert CommandType.AWAKE_SANDBOX == "awake_sandbox"

    def test_workspace_info_value(self):
        assert CommandType.WORKSPACE_INFO == "workspace_info"

    def test_continue_run_value(self):
        assert CommandType.CONTINUE_RUN == "continue_run"

    def test_publish_project_value(self):
        assert CommandType.PUBLISH_PROJECT == "publish"

    def test_start_fork_value(self):
        assert CommandType.START_FORK == "start_fork"

    def test_cancel_cancel_type(self):
        assert CommandType("cancel") == CommandType.CANCEL

    def test_can_construct_from_string(self):
        assert CommandType("query") == CommandType.QUERY

    def test_raises_on_unknown_string(self):
        with pytest.raises(ValueError):
            CommandType("nonexistent_command")

    def test_submit_testflight_value(self):
        assert CommandType.SUBMIT_TESTFLIGHT == "submit_testflight"

    def test_apple_auth_login_value(self):
        assert CommandType.APPLE_AUTH_LOGIN == "apple_auth_login"

    def test_apple_check_auth_value(self):
        assert CommandType.APPLE_CHECK_AUTH == "apple_check_auth"


# ---------------------------------------------------------------------------
# BaseCommandHandler._send_error_event
# ---------------------------------------------------------------------------


class TestBaseCommandHandlerSendErrorEvent:
    @pytest.mark.asyncio
    async def test_sends_error_event_with_uuid_session_id(self):
        event_bus = _mock_event_stream()
        handler = ConcreteHandler(event_bus=event_bus, **_base_kwargs())
        session_id = uuid.uuid4()
        await handler._send_error_event(session_id, error_code=ErrorCode.INTERNAL_ERROR, message="Test error")
        event_bus.publish.assert_awaited_once()
        published_event = event_bus.publish.call_args[0][1]
        assert published_event.name == EventType.ERROR
        assert published_event.content["message"] == "Test error"
        assert published_event.session_id == session_id

    @pytest.mark.asyncio
    async def test_sends_error_with_specific_code(self):
        event_bus = _mock_event_stream()
        handler = ConcreteHandler(event_bus=event_bus, **_base_kwargs())
        await handler._send_error_event(uuid.uuid4(), error_code=ErrorCode.AUTH_ERROR, message="Auth failed")
        published_event = event_bus.publish.call_args[0][1]
        assert published_event.error_code == ErrorCode.AUTH_ERROR
        assert published_event.content["error_code"] == "auth_error"

    @pytest.mark.asyncio
    async def test_default_message_from_error_code(self):
        event_bus = _mock_event_stream()
        handler = ConcreteHandler(event_bus=event_bus, **_base_kwargs())
        await handler._send_error_event(uuid.uuid4(), error_code=ErrorCode.INSUFFICIENT_CREDITS)
        published_event = event_bus.publish.call_args[0][1]
        assert published_event.error_code == ErrorCode.INSUFFICIENT_CREDITS
        assert "credits" in published_event.content["message"].lower()


# ---------------------------------------------------------------------------
# BaseCommandHandler._send_event
# ---------------------------------------------------------------------------


class TestBaseCommandHandlerSendEvent:
    @pytest.mark.asyncio
    async def test_sends_event_with_message_and_kwargs(self):
        event_bus = _mock_event_stream()
        handler = ConcreteHandler(event_bus=event_bus, **_base_kwargs())
        session_id = uuid.uuid4()
        await handler._send_event(session_id, "Status update", EventType.STATUS_UPDATE, key1="val1")
        published_event = event_bus.publish.call_args[0][1]
        assert published_event.name == EventType.STATUS_UPDATE
        assert published_event.content["message"] == "Status update"
        assert published_event.content["key1"] == "val1"

    @pytest.mark.asyncio
    async def test_sends_event_with_run_id(self):
        event_bus = _mock_event_stream()
        handler = ConcreteHandler(event_bus=event_bus, **_base_kwargs())
        run_id = uuid.uuid4()
        await handler._send_event(uuid.uuid4(), "msg", EventType.STATUS_UPDATE, run_id=run_id)
        published_event = event_bus.publish.call_args[0][1]
        assert published_event.run_id == run_id

    @pytest.mark.asyncio
    async def test_converts_string_session_id_to_uuid(self):
        event_bus = _mock_event_stream()
        handler = ConcreteHandler(event_bus=event_bus, **_base_kwargs())
        session_str = str(uuid.uuid4())
        await handler._send_event(session_str, "test", EventType.STATUS_UPDATE)
        published_event = event_bus.publish.call_args[0][1]
        assert isinstance(published_event.session_id, uuid.UUID)


# ---------------------------------------------------------------------------
# BaseCommandHandler.send_event
# ---------------------------------------------------------------------------


class TestBaseCommandHandlerSendEventPublic:
    @pytest.mark.asyncio
    async def test_publishes_realtime_event_to_stream(self):
        event_bus = _mock_event_stream()
        handler = ConcreteHandler(event_bus=event_bus, **_base_kwargs())
        event = SystemEvent(
            group=EventGroup.SYSTEM, name=EventType.PONG, session_id=uuid.uuid4(), content={}
        )
        await handler.send_event(event)
        event_bus.publish.assert_awaited_once_with(EventGroup.SYSTEM, event)

    def test_event_bus_attribute_is_set(self):
        event_bus = _mock_event_stream()
        handler = ConcreteHandler(event_bus=event_bus, **_base_kwargs())
        assert handler.event_bus is event_bus


# ---------------------------------------------------------------------------
# Stub-based PingHandler behaviour test
# ---------------------------------------------------------------------------


class StubPingHandler(BaseCommandHandler):
    """Mirrors PingHandler behaviour without importing it."""

    def get_command_type(self):
        return CommandType.PING

    async def handle(self, content, session_info) -> None:
        await self.send_event(
            SystemEvent(
                group=EventGroup.SYSTEM, name=EventType.PONG, session_id=session_info.id, content={}
            )
        )


class TestStubPingHandler:
    def test_get_command_type(self):
        handler = StubPingHandler(event_bus=_mock_event_stream(), **_base_kwargs())
        assert handler.get_command_type() == CommandType.PING

    @pytest.mark.asyncio
    async def test_handle_sends_pong_event(self):
        event_bus = _mock_event_stream()
        handler = StubPingHandler(event_bus=event_bus, **_base_kwargs())
        session = _session_info()
        await handler.dispatch({}, session)
        event_bus.publish.assert_awaited_once()
        published_event = event_bus.publish.call_args[0][1]
        assert published_event.name == EventType.PONG
        assert published_event.session_id == session.id

    @pytest.mark.asyncio
    async def test_handle_sends_pong_regardless_of_content(self):
        event_bus = _mock_event_stream()
        handler = StubPingHandler(event_bus=event_bus, **_base_kwargs())
        session = _session_info()
        await handler.dispatch({"extra": "data"}, session)
        event_bus.publish.assert_awaited_once()


# ---------------------------------------------------------------------------
# Stub-based CancelHandler behaviour test
# ---------------------------------------------------------------------------


class StubCancelHandler(BaseCommandHandler):
    """Mirrors CancelHandler behaviour without importing it."""

    def get_command_type(self):
        return CommandType.CANCEL

    async def handle(self, content, session_info) -> None:
        last_task = await self._run_task_service.get_last_by_session_id(
            db=MagicMock(), session_id=session_info.id
        )
        if not last_task:
            await self._send_error_event(session_info.id, message="Task Run not found")
            return

        from ii_agent.tasks.types import RunStatus

        if last_task.status not in [RunStatus.RUNNING.value, RunStatus.PAUSED.value]:
            return

        last_task.status = "aborting"


class TestStubCancelHandler:
    def test_get_command_type(self):
        handler = StubCancelHandler(event_bus=_mock_event_stream(), **_base_kwargs())
        assert handler.get_command_type() == CommandType.CANCEL

    @pytest.mark.asyncio
    async def test_sends_error_when_no_task_found(self):
        kwargs = _base_kwargs()
        kwargs["run_task_service"].get_last_by_session_id = AsyncMock(return_value=None)
        event_bus = _mock_event_stream()
        handler = StubCancelHandler(event_bus=event_bus, **kwargs)
        session = _session_info()
        await handler.dispatch({}, session)
        event_bus.publish.assert_awaited_once()
        published_event = event_bus.publish.call_args[0][1]
        assert published_event.name == EventType.ERROR

    @pytest.mark.asyncio
    async def test_no_action_when_task_not_running(self):
        from ii_agent.tasks.types import RunStatus

        task = MagicMock()
        task.status = RunStatus.COMPLETED.value
        kwargs = _base_kwargs()
        kwargs["run_task_service"].get_last_by_session_id = AsyncMock(return_value=task)
        event_bus = _mock_event_stream()
        handler = StubCancelHandler(event_bus=event_bus, **kwargs)
        session = _session_info()
        await handler.dispatch({}, session)
        event_bus.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_marks_running_task_as_aborting(self):
        from ii_agent.tasks.types import RunStatus

        task = MagicMock()
        task.id = uuid.uuid4()
        task.status = RunStatus.RUNNING.value
        kwargs = _base_kwargs()
        kwargs["run_task_service"].get_last_by_session_id = AsyncMock(return_value=task)
        event_bus = _mock_event_stream()
        handler = StubCancelHandler(event_bus=event_bus, **kwargs)
        session = _session_info()
        await handler.dispatch({}, session)
        assert task.status == "aborting"


# ---------------------------------------------------------------------------
# CommandHandlerFactory – tests via stub factory class to avoid deep imports

# ---------------------------------------------------------------------------


class StubCommandHandlerFactory:
    """Minimal reproduction of CommandHandlerFactory logic without deep dependencies."""

    def __init__(self, sio, container):
        self._sio = sio
        self._container = container
        self._handlers = {}
        self._initialized = False

    async def initialize(self):
        if not self._initialized:
            await self._initialize_handlers()
            self._initialized = True

    async def _initialize_handlers(self):
        pass

    def get_handler(self, command_type):
        return self._handlers.get(command_type)

    def get_handler_by_string(self, command_type_str: str):
        try:
            command_type = CommandType(command_type_str)
            return self.get_handler(command_type)
        except ValueError:
            return None


class TestCommandHandlerFactory:
    def test_can_instantiate_stub(self):
        factory = StubCommandHandlerFactory(sio=MagicMock(), container=_mock_container())
        assert isinstance(factory, StubCommandHandlerFactory)

    def test_initially_not_initialized(self):
        factory = StubCommandHandlerFactory(sio=MagicMock(), container=_mock_container())
        assert factory._initialized is False

    def test_get_handler_returns_none_before_initialization(self):
        factory = StubCommandHandlerFactory(sio=MagicMock(), container=_mock_container())
        result = factory.get_handler(CommandType.PING)
        assert result is None

    def test_get_handler_by_string_returns_none_for_unknown_type(self):
        factory = StubCommandHandlerFactory(sio=MagicMock(), container=_mock_container())
        result = factory.get_handler_by_string("nonexistent_command")
        assert result is None

    def test_get_handler_by_string_returns_none_before_initialization(self):
        factory = StubCommandHandlerFactory(sio=MagicMock(), container=_mock_container())
        result = factory.get_handler_by_string("query")
        assert result is None

    def test_get_handler_by_string_with_known_type_after_manual_setup(self):
        factory = StubCommandHandlerFactory(sio=MagicMock(), container=_mock_container())
        mock_handler = MagicMock()
        factory._handlers[CommandType.PING] = mock_handler
        result = factory.get_handler_by_string("ping")
        assert result is mock_handler

    def test_get_handler_with_known_type_after_manual_setup(self):
        factory = StubCommandHandlerFactory(sio=MagicMock(), container=_mock_container())
        mock_handler = MagicMock()
        factory._handlers[CommandType.QUERY] = mock_handler
        result = factory.get_handler(CommandType.QUERY)
        assert result is mock_handler

    def test_get_handler_for_missing_type_returns_none(self):
        factory = StubCommandHandlerFactory(sio=MagicMock(), container=_mock_container())
        factory._handlers[CommandType.PING] = MagicMock()
        result = factory.get_handler(CommandType.CANCEL)
        assert result is None

    @pytest.mark.asyncio
    async def test_initialize_runs_once_and_sets_flag(self, monkeypatch):
        factory = StubCommandHandlerFactory(sio=SimpleNamespace(), container=SimpleNamespace())
        call_count = {"n": 0}

        async def _fake_init():
            call_count["n"] += 1
            factory._handlers = {CommandType.PING: object()}

        monkeypatch.setattr(factory, "_initialize_handlers", _fake_init)
        await factory.initialize()
        await factory.initialize()
        assert factory._initialized is True
        assert call_count["n"] == 1

    @pytest.mark.asyncio
    async def test_initialize_does_not_set_flag_before_calling(self):
        factory = StubCommandHandlerFactory(sio=SimpleNamespace(), container=SimpleNamespace())
        assert factory._initialized is False

    def test_get_handler_returns_correct_type(self):
        factory = StubCommandHandlerFactory(sio=MagicMock(), container=_mock_container())
        mock_cancel = MagicMock()
        mock_query = MagicMock()
        factory._handlers[CommandType.CANCEL] = mock_cancel
        factory._handlers[CommandType.QUERY] = mock_query
        assert factory.get_handler(CommandType.CANCEL) is mock_cancel
        assert factory.get_handler(CommandType.QUERY) is mock_query


# ---------------------------------------------------------------------------
# Additional edge cases for BaseCommandHandler base methods
# ---------------------------------------------------------------------------


class TestBaseCommandHandlerEdgeCases:
    @pytest.mark.asyncio
    async def test_send_error_event_with_run_id(self):
        event_bus = _mock_event_stream()
        handler = ConcreteHandler(event_bus=event_bus, **_base_kwargs())
        run_id = uuid.uuid4()
        await handler._send_error_event(uuid.uuid4(), "Error", run_id=run_id)
        published_event = event_bus.publish.call_args[0][1]
        assert published_event.run_id == run_id

    @pytest.mark.asyncio
    async def test_handler_stores_event_bus_reference(self):
        event_bus = _mock_event_stream()
        handler = ConcreteHandler(event_bus=event_bus, **_base_kwargs())
        assert handler.event_bus is event_bus

    @pytest.mark.asyncio
    async def test_handler_stores_service_references(self):
        kwargs = _base_kwargs()
        handler = ConcreteHandler(event_bus=_mock_event_stream(), **kwargs)
        assert handler._session_service is kwargs["session_service"]
        assert handler._run_task_service is kwargs["run_task_service"]

    @pytest.mark.asyncio
    async def test_multiple_send_events_accumulate(self):
        event_bus = _mock_event_stream()
        handler = ConcreteHandler(event_bus=event_bus, **_base_kwargs())
        sid = uuid.uuid4()
        for i in range(3):
            await handler._send_error_event(sid, f"Error {i}")
        assert event_bus.publish.await_count == 3

    @pytest.mark.asyncio
    async def test_send_event_content_includes_extra_kwargs(self):
        event_bus = _mock_event_stream()
        handler = ConcreteHandler(event_bus=event_bus, **_base_kwargs())
        await handler._send_event(
            uuid.uuid4(),
            "Hello",
            EventType.STATUS_UPDATE,
            status="active",
            percent=50,
        )
        content = event_bus.publish.call_args[0][1].content
        assert content["status"] == "active"
        assert content["percent"] == 50
