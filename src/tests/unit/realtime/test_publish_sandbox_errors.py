from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from ii_agent.agents.sandboxes.live_terminal_service import LiveTerminalService
from ii_agent.core.exceptions import ServiceUnavailableError
from ii_agent.realtime.events.app_events import ErrorCode
from ii_agent.sessions.schemas import SessionInfo

pytestmark = pytest.mark.unit


class CapturingEventStream:
    def __init__(self) -> None:
        self.events: list = []

    async def publish(self, event) -> None:
        self.events.append(event)

    def events_of_name(self, event_name: str) -> list:
        return [event for event in self.events if getattr(event, "name", None) == event_name]


@asynccontextmanager
async def _noop_db_cm():
    yield None


def _make_session_info(*, api_version: str = "v1") -> SessionInfo:
    return SessionInfo(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        api_version=api_version,
        name="Test Session",
        status="active",
        workspace_dir="/workspace/app",
        is_public=False,
        created_at="2024-01-01T00:00:00Z",
        agent_type="general",
    )


@pytest.mark.asyncio
async def test_publish_handler_reports_sandbox_connection_failure():
    from ii_agent.realtime.handlers.publish import PublishProjectHandler

    stream = CapturingEventStream()
    container = SimpleNamespace(
        project_service=SimpleNamespace(get_session_project_or_none=AsyncMock(return_value=None)),
        deployments_service=SimpleNamespace(update_deployment_status=AsyncMock()),
        sandbox_service=SimpleNamespace(
            get_sandbox_for_session=AsyncMock(side_effect=RuntimeError("e2b unavailable"))
        ),
    )
    handler = PublishProjectHandler(pubsub=stream, container=container)

    with patch(
        "ii_agent.realtime.handlers.publish.get_db_session_local",
        new=lambda: _noop_db_cm(),
    ):
        await handler.dispatch({"vercel_api_key": "token"}, _make_session_info())

    errors = stream.events_of_name("system.error")
    assert len(errors) == 1
    assert errors[0].error_code == ErrorCode.SANDBOX_CONNECTION_FAILED
    assert "e2b unavailable" in errors[0].content["message"]


@pytest.mark.asyncio
async def test_publish_handler_reports_missing_sandbox_without_raising():
    from ii_agent.realtime.handlers.publish import PublishProjectHandler

    stream = CapturingEventStream()
    container = SimpleNamespace(
        project_service=SimpleNamespace(get_session_project_or_none=AsyncMock(return_value=None)),
        deployments_service=SimpleNamespace(update_deployment_status=AsyncMock()),
        sandbox_service=SimpleNamespace(get_sandbox_for_session=AsyncMock(return_value=None)),
    )
    handler = PublishProjectHandler(pubsub=stream, container=container)

    with patch(
        "ii_agent.realtime.handlers.publish.get_db_session_local",
        new=lambda: _noop_db_cm(),
    ):
        await handler.dispatch({"vercel_api_key": "token"}, _make_session_info())

    errors = stream.events_of_name("system.error")
    assert len(errors) == 1
    assert errors[0].error_code == ErrorCode.SANDBOX_CONNECTION_FAILED
    assert "No active sandbox" in errors[0].content["message"]


@pytest.mark.asyncio
async def test_cloud_run_publish_handler_reports_sandbox_connection_failure():
    from ii_agent.realtime.handlers.cloud_run_publish import CloudRunPublishHandler

    stream = CapturingEventStream()
    container = SimpleNamespace(
        project_service=SimpleNamespace(get_session_project_or_none=AsyncMock(return_value=None)),
        deployments_service=SimpleNamespace(update_deployment_status=AsyncMock()),
    )
    handler = CloudRunPublishHandler(pubsub=stream, container=container)
    handler._get_sandbox = AsyncMock(side_effect=RuntimeError("provider down"))

    with patch(
        "ii_agent.realtime.handlers.cloud_run_publish.get_db_session_local",
        new=lambda: _noop_db_cm(),
    ):
        await handler.dispatch(
            {"project_path": "/workspace/app", "project_name": "app"},
            _make_session_info(),
        )

    errors = stream.events_of_name("system.error")
    assert len(errors) == 1
    assert errors[0].error_code == ErrorCode.SANDBOX_CONNECTION_FAILED
    assert "provider down" in errors[0].content["message"]


@pytest.mark.asyncio
async def test_cloud_run_publish_handler_reports_missing_sandbox_without_raising():
    from ii_agent.realtime.handlers.cloud_run_publish import CloudRunPublishHandler

    stream = CapturingEventStream()
    container = SimpleNamespace(
        project_service=SimpleNamespace(get_session_project_or_none=AsyncMock(return_value=None)),
        deployments_service=SimpleNamespace(update_deployment_status=AsyncMock()),
    )
    handler = CloudRunPublishHandler(pubsub=stream, container=container)
    handler._get_sandbox = AsyncMock(return_value=None)

    with patch(
        "ii_agent.realtime.handlers.cloud_run_publish.get_db_session_local",
        new=lambda: _noop_db_cm(),
    ):
        await handler.dispatch(
            {"project_path": "/workspace/app", "project_name": "app"},
            _make_session_info(),
        )

    errors = stream.events_of_name("system.error")
    assert len(errors) == 1
    assert errors[0].error_code == ErrorCode.SANDBOX_CONNECTION_FAILED
    assert "No active sandbox" in errors[0].content["message"]


@pytest.mark.asyncio
async def test_cloud_run_get_sandbox_uses_sandbox_service_resolution():
    from ii_agent.realtime.handlers.cloud_run_publish import CloudRunPublishHandler

    expected_sandbox = object()
    container = SimpleNamespace(
        sandbox_service=SimpleNamespace(
            get_sandbox_for_session=AsyncMock(return_value=expected_sandbox)
        )
    )
    handler = CloudRunPublishHandler(pubsub=CapturingEventStream(), container=container)
    session_info = _make_session_info()

    with patch(
        "ii_agent.realtime.handlers.cloud_run_publish.get_db_session_local",
        new=lambda: _noop_db_cm(),
    ):
        sandbox = await handler._get_sandbox(session_info, container)

    assert sandbox is expected_sandbox
    container.sandbox_service.get_sandbox_for_session.assert_awaited_once_with(
        None,
        session_id=session_info.id,
    )


@pytest.mark.asyncio
async def test_preview_sandbox_file_translates_connection_errors():
    from ii_agent.agents.sandboxes.router import preview_sandbox_file

    session_id = uuid.uuid4()
    current_user = SimpleNamespace(id=uuid.uuid4())
    session = SimpleNamespace(project=None)
    session_repo = SimpleNamespace(get_by_id_and_user=AsyncMock(return_value=session))
    sandbox_service = SimpleNamespace(
        get_sandbox_for_session=AsyncMock(side_effect=RuntimeError("provider down"))
    )

    with pytest.raises(ServiceUnavailableError, match="Failed to connect to the sandbox"):
        await preview_sandbox_file(
            session_id=session_id,
            current_user=current_user,
            db=None,
            session_repo=session_repo,
            sandbox_service=sandbox_service,
            path="/workspace/image.png",
        )


@pytest.mark.asyncio
async def test_live_terminal_create_terminal_emits_error_when_sandbox_connection_fails():
    sio = SimpleNamespace(emit=AsyncMock())
    sandbox_service = SimpleNamespace(
        get_sandbox_for_session=AsyncMock(side_effect=RuntimeError("provider down"))
    )
    service = LiveTerminalService(sandbox_service=sandbox_service)
    service.bind_socketio(sio)

    with patch(
        "ii_agent.agents.sandboxes.live_terminal_service.get_db_session_local",
        new=lambda: _noop_db_cm(),
    ):
        await service.create_terminal(
            "sid-1",
            session_info=_make_session_info(),
            terminal_id="term-1",
            cols=120,
            rows=40,
        )

    sio.emit.assert_awaited_once_with(
        "pty_error",
        {
            "terminal_id": "term-1",
            "message": "Unable to start terminal",
        },
        room="sid-1",
    )
