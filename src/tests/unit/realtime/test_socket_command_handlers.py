"""Unit tests for realtime socket command handler pure logic.

Note: We avoid importing handler classes directly (PingHandler, CancelHandler, etc.)
because those have transitive deep dependencies (e.g., google.genai) that may not
be present in all environments. We test behaviour via duck-typing stubs and the
abstract base class alone.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.realtime.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)
from ii_agent.realtime.events.models import EventType, RealtimeEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_event_stream():
    stream = MagicMock()
    stream.publish = AsyncMock()
    return stream


def _mock_container():
    container = MagicMock()
    container.agent_run_service = MagicMock()
    container.agent_run_service.get_last_by_session_id = AsyncMock()
    container.agent_run_service.get_running_task = AsyncMock()
    container.agent_run_service.create_task = AsyncMock()
    container.event_service = MagicMock()
    container.event_service.save_event = AsyncMock()
    container.file_service = MagicMock()
    container.file_service.get_file_by_id = AsyncMock()
    container.session_validation_service = MagicMock()
    container.session_validation_service.validate_and_prepare_session = AsyncMock()
    container.llm_setting_service = MagicMock()
    return container


def _session_info(session_id: str = None, user_id: str = "u1"):
    info = MagicMock()
    info.id = uuid.UUID(session_id) if session_id else uuid.uuid4()
    info.user_id = user_id
    info.name = "Test session"
    return info


class ConcreteHandler(CommandHandler):
    """Concrete implementation for testing abstract methods."""

    _cmd_type = UserCommandType.PING

    def get_command_type(self) -> UserCommandType:
        return self._cmd_type

    async def handle(self, content, session_info) -> None:
        pass


# ---------------------------------------------------------------------------
# UserCommandType enum
# ---------------------------------------------------------------------------

class TestUserCommandType:
    def test_query_value(self):
        assert UserCommandType.QUERY == "query"

    def test_cancel_value(self):
        assert UserCommandType.CANCEL == "cancel"

    def test_ping_value(self):
        assert UserCommandType.PING == "ping"

    def test_plan_value(self):
        assert UserCommandType.PLAN == "plan"

    def test_sandbox_status_value(self):
        assert UserCommandType.SANDBOX_STATUS == "sandbox_status"

    def test_awake_sandbox_value(self):
        assert UserCommandType.AWAKE_SANDBOX == "awake_sandbox"

    def test_workspace_info_value(self):
        assert UserCommandType.WORKSPACE_INFO == "workspace_info"

    def test_continue_run_value(self):
        assert UserCommandType.CONTINUE_RUN == "continue_run"

    def test_enhance_prompt_value(self):
        assert UserCommandType.ENHANCE_PROMPT == "enhance_prompt"

    def test_publish_project_value(self):
        assert UserCommandType.PUBLISH_PROJECT == "publish"

    def test_start_fork_value(self):
        assert UserCommandType.START_FORK == "start_fork"

    def test_cancel_cancel_type(self):
        assert UserCommandType("cancel") == UserCommandType.CANCEL

    def test_can_construct_from_string(self):
        assert UserCommandType("query") == UserCommandType.QUERY

    def test_raises_on_unknown_string(self):
        with pytest.raises(ValueError):
            UserCommandType("nonexistent_command")

    def test_submit_testflight_value(self):
        assert UserCommandType.SUBMIT_TESTFLIGHT == "submit_testflight"

    def test_apple_auth_login_value(self):
        assert UserCommandType.APPLE_AUTH_LOGIN == "apple_auth_login"

    def test_apple_check_auth_value(self):
        assert UserCommandType.APPLE_CHECK_AUTH == "apple_check_auth"


# ---------------------------------------------------------------------------
# CommandHandler._send_error_event
# ---------------------------------------------------------------------------

class TestCommandHandlerSendErrorEvent:
    @pytest.mark.asyncio
    async def test_sends_error_event_with_string_session_id(self):
        event_stream = _mock_event_stream()
        handler = ConcreteHandler(event_stream=event_stream, container=_mock_container())
        session_id = str(uuid.uuid4())
        await handler._send_error_event(session_id, "Test error")
        event_stream.publish.assert_awaited_once()
        published_event = event_stream.publish.call_args[0][0]
        assert published_event.type == EventType.ERROR
        assert published_event.content["message"] == "Test error"

    @pytest.mark.asyncio
    async def test_sends_error_event_with_uuid_session_id(self):
        event_stream = _mock_event_stream()
        handler = ConcreteHandler(event_stream=event_stream, container=_mock_container())
        session_id = uuid.uuid4()
        await handler._send_error_event(session_id, "uuid error")
        published_event = event_stream.publish.call_args[0][0]
        assert published_event.session_id == session_id

    @pytest.mark.asyncio
    async def test_sends_custom_error_type(self):
        event_stream = _mock_event_stream()
        handler = ConcreteHandler(event_stream=event_stream, container=_mock_container())
        await handler._send_error_event(uuid.uuid4(), "Error msg", error_type="custom_error")
        published_event = event_stream.publish.call_args[0][0]
        assert published_event.content["error_type"] == "custom_error"

    @pytest.mark.asyncio
    async def test_default_error_type_is_error(self):
        event_stream = _mock_event_stream()
        handler = ConcreteHandler(event_stream=event_stream, container=_mock_container())
        await handler._send_error_event(uuid.uuid4(), "Err")
        published_event = event_stream.publish.call_args[0][0]
        assert published_event.content["error_type"] == "error"


# ---------------------------------------------------------------------------
# CommandHandler._send_event
# ---------------------------------------------------------------------------

class TestCommandHandlerSendEvent:
    @pytest.mark.asyncio
    async def test_sends_event_with_message_and_kwargs(self):
        event_stream = _mock_event_stream()
        handler = ConcreteHandler(event_stream=event_stream, container=_mock_container())
        session_id = uuid.uuid4()
        await handler._send_event(
            session_id, "Status update", EventType.STATUS_UPDATE, key1="val1"
        )
        published_event = event_stream.publish.call_args[0][0]
        assert published_event.type == EventType.STATUS_UPDATE
        assert published_event.content["message"] == "Status update"
        assert published_event.content["key1"] == "val1"

    @pytest.mark.asyncio
    async def test_sends_event_with_run_id(self):
        event_stream = _mock_event_stream()
        handler = ConcreteHandler(event_stream=event_stream, container=_mock_container())
        run_id = uuid.uuid4()
        await handler._send_event(
            uuid.uuid4(), "msg", EventType.STATUS_UPDATE, run_id=run_id
        )
        published_event = event_stream.publish.call_args[0][0]
        assert published_event.run_id == run_id

    @pytest.mark.asyncio
    async def test_converts_string_session_id_to_uuid(self):
        event_stream = _mock_event_stream()
        handler = ConcreteHandler(event_stream=event_stream, container=_mock_container())
        session_str = str(uuid.uuid4())
        await handler._send_event(session_str, "test", EventType.STATUS_UPDATE)
        published_event = event_stream.publish.call_args[0][0]
        assert isinstance(published_event.session_id, uuid.UUID)


# ---------------------------------------------------------------------------
# CommandHandler.send_event
# ---------------------------------------------------------------------------

class TestCommandHandlerSendEventPublic:
    @pytest.mark.asyncio
    async def test_publishes_realtime_event_to_stream(self):
        event_stream = _mock_event_stream()
        handler = ConcreteHandler(event_stream=event_stream, container=_mock_container())
        event = RealtimeEvent(type=EventType.PONG, session_id=uuid.uuid4(), content={})
        await handler.send_event(event)
        event_stream.publish.assert_awaited_once_with(event)

    def test_get_event_stream_returns_stream(self):
        event_stream = _mock_event_stream()
        handler = ConcreteHandler(event_stream=event_stream, container=_mock_container())
        assert handler.get_event_stream() is event_stream


# ---------------------------------------------------------------------------
# Stub-based PingHandler behaviour test
# ---------------------------------------------------------------------------

class StubPingHandler(CommandHandler):
    """Mirrors PingHandler behaviour without importing it."""

    def get_command_type(self):
        return UserCommandType.PING

    async def handle(self, content, session_info) -> None:
        from ii_agent.realtime.events.models import RealtimeEvent, EventType
        await self.send_event(
            RealtimeEvent(type=EventType.PONG, session_id=session_info.id, content={})
        )


class TestStubPingHandler:
    def test_get_command_type(self):
        handler = StubPingHandler(event_stream=_mock_event_stream(), container=_mock_container())
        assert handler.get_command_type() == UserCommandType.PING

    @pytest.mark.asyncio
    async def test_handle_sends_pong_event(self):
        event_stream = _mock_event_stream()
        handler = StubPingHandler(event_stream=event_stream, container=_mock_container())
        session = _session_info()
        await handler.handle({}, session)
        event_stream.publish.assert_awaited_once()
        published_event = event_stream.publish.call_args[0][0]
        assert published_event.type == EventType.PONG
        assert published_event.session_id == session.id

    @pytest.mark.asyncio
    async def test_handle_sends_pong_regardless_of_content(self):
        event_stream = _mock_event_stream()
        handler = StubPingHandler(event_stream=event_stream, container=_mock_container())
        session = _session_info()
        await handler.handle({"extra": "data"}, session)
        event_stream.publish.assert_awaited_once()


# ---------------------------------------------------------------------------
# Stub-based CancelHandler behaviour test
# ---------------------------------------------------------------------------

class StubCancelHandler(CommandHandler):
    """Mirrors CancelHandler behaviour without importing it."""

    def get_command_type(self):
        return UserCommandType.CANCEL

    async def handle(self, content, session_info) -> None:
        last_task = await self.container.agent_run_service.get_last_by_session_id(
            db=MagicMock(), session_id=session_info.id
        )
        if not last_task:
            await self._send_error_event(session_info.id, message="Task Run not found")
            return

        from ii_agent.agent.agents.models import RunStatus
        if last_task.status not in [RunStatus.RUNNING.value, RunStatus.PAUSED.value]:
            return

        last_task.status = "aborting"


class TestStubCancelHandler:
    def test_get_command_type(self):
        handler = StubCancelHandler(event_stream=_mock_event_stream(), container=_mock_container())
        assert handler.get_command_type() == UserCommandType.CANCEL

    @pytest.mark.asyncio
    async def test_sends_error_when_no_task_found(self):
        container = _mock_container()
        container.agent_run_service.get_last_by_session_id = AsyncMock(return_value=None)
        event_stream = _mock_event_stream()
        handler = StubCancelHandler(event_stream=event_stream, container=container)
        session = _session_info()
        await handler.handle({}, session)
        event_stream.publish.assert_awaited_once()
        published_event = event_stream.publish.call_args[0][0]
        assert published_event.type == EventType.ERROR

    @pytest.mark.asyncio
    async def test_no_action_when_task_not_running(self):
        from ii_agent.agent.agents.models import RunStatus
        task = MagicMock()
        task.status = RunStatus.COMPLETED.value
        container = _mock_container()
        container.agent_run_service.get_last_by_session_id = AsyncMock(return_value=task)
        event_stream = _mock_event_stream()
        handler = StubCancelHandler(event_stream=event_stream, container=container)
        session = _session_info()
        await handler.handle({}, session)
        event_stream.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_marks_running_task_as_aborting(self):
        from ii_agent.agent.agents.models import RunStatus
        task = MagicMock()
        task.id = uuid.uuid4()
        task.status = RunStatus.RUNNING.value
        container = _mock_container()
        container.agent_run_service.get_last_by_session_id = AsyncMock(return_value=task)
        event_stream = _mock_event_stream()
        handler = StubCancelHandler(event_stream=event_stream, container=container)
        session = _session_info()
        await handler.handle({}, session)
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
            command_type = UserCommandType(command_type_str)
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
        result = factory.get_handler(UserCommandType.PING)
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
        factory._handlers[UserCommandType.PING] = mock_handler
        result = factory.get_handler_by_string("ping")
        assert result is mock_handler

    def test_get_handler_with_known_type_after_manual_setup(self):
        factory = StubCommandHandlerFactory(sio=MagicMock(), container=_mock_container())
        mock_handler = MagicMock()
        factory._handlers[UserCommandType.QUERY] = mock_handler
        result = factory.get_handler(UserCommandType.QUERY)
        assert result is mock_handler

    def test_get_handler_for_missing_type_returns_none(self):
        factory = StubCommandHandlerFactory(sio=MagicMock(), container=_mock_container())
        factory._handlers[UserCommandType.PING] = MagicMock()
        result = factory.get_handler(UserCommandType.CANCEL)
        assert result is None

    @pytest.mark.asyncio
    async def test_initialize_runs_once_and_sets_flag(self, monkeypatch):
        factory = StubCommandHandlerFactory(sio=SimpleNamespace(), container=SimpleNamespace())
        call_count = {"n": 0}

        async def _fake_init():
            call_count["n"] += 1
            factory._handlers = {UserCommandType.PING: object()}

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
        factory._handlers[UserCommandType.CANCEL] = mock_cancel
        factory._handlers[UserCommandType.QUERY] = mock_query
        assert factory.get_handler(UserCommandType.CANCEL) is mock_cancel
        assert factory.get_handler(UserCommandType.QUERY) is mock_query


# ---------------------------------------------------------------------------
# Additional edge cases for CommandHandler base methods
# ---------------------------------------------------------------------------

class TestCommandHandlerEdgeCases:
    @pytest.mark.asyncio
    async def test_send_error_event_with_run_id(self):
        event_stream = _mock_event_stream()
        handler = ConcreteHandler(event_stream=event_stream, container=_mock_container())
        run_id = uuid.uuid4()
        await handler._send_error_event(uuid.uuid4(), "Error", run_id=run_id)
        published_event = event_stream.publish.call_args[0][0]
        assert published_event.run_id == run_id

    @pytest.mark.asyncio
    async def test_handler_stores_container_reference(self):
        container = _mock_container()
        handler = ConcreteHandler(event_stream=_mock_event_stream(), container=container)
        assert handler.container is container

    @pytest.mark.asyncio
    async def test_handler_stores_event_stream_reference(self):
        event_stream = _mock_event_stream()
        handler = ConcreteHandler(event_stream=event_stream, container=_mock_container())
        assert handler.event_stream is event_stream

    @pytest.mark.asyncio
    async def test_multiple_send_events_accumulate(self):
        event_stream = _mock_event_stream()
        handler = ConcreteHandler(event_stream=event_stream, container=_mock_container())
        sid = uuid.uuid4()
        for i in range(3):
            await handler._send_error_event(sid, f"Error {i}")
        assert event_stream.publish.await_count == 3

    @pytest.mark.asyncio
    async def test_send_event_content_includes_extra_kwargs(self):
        event_stream = _mock_event_stream()
        handler = ConcreteHandler(event_stream=event_stream, container=_mock_container())
        await handler._send_event(
            uuid.uuid4(),
            "Hello",
            EventType.STATUS_UPDATE,
            status="active",
            percent=50,
        )
        content = event_stream.publish.call_args[0][0].content
        assert content["status"] == "active"
        assert content["percent"] == 50
