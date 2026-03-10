from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ii_agent.mobile.apple import AppleAuthStateEnum
from ii_agent.core.events.models import EventType
from ii_agent.realtime.socket.command.submit_testflight_handler import (
    SubmitTestflightHandler,
)


def _make_handler(fake_event_stream):
    container = SimpleNamespace(
        sandbox_service=SimpleNamespace(),
        session_service=SimpleNamespace(),
        project_service=SimpleNamespace(),
        config=SimpleNamespace(mcp=SimpleNamespace(port=8080)),
    )
    return SubmitTestflightHandler(event_stream=fake_event_stream, container=container)


def _session_info():
    return SimpleNamespace(
        id=uuid4(),
        user_id="user-1",
    )


@pytest.mark.asyncio
async def test_handle_requires_apple_authentication(fake_event_stream, monkeypatch):
    handler = _make_handler(fake_event_stream)
    handler._send_error_event = AsyncMock()

    monkeypatch.setattr(
        "ii_agent.realtime.socket.command.submit_testflight_handler.AppleCredentials.get_active_session",
        AsyncMock(return_value=None),
    )

    await handler.handle({}, _session_info())

    handler._send_error_event.assert_awaited_once()
    kwargs = handler._send_error_event.await_args.kwargs
    assert kwargs["error_type"] == "auth_error"
    assert "authenticate with Apple first" in kwargs["message"]


@pytest.mark.asyncio
async def test_handle_rejects_incomplete_apple_auth(fake_event_stream, monkeypatch):
    handler = _make_handler(fake_event_stream)
    handler._send_error_event = AsyncMock()

    credential = SimpleNamespace(auth_state="pending")
    monkeypatch.setattr(
        "ii_agent.realtime.socket.command.submit_testflight_handler.AppleCredentials.get_active_session",
        AsyncMock(return_value=credential),
    )

    await handler.handle({}, _session_info())

    kwargs = handler._send_error_event.await_args.kwargs
    assert kwargs["error_type"] == "auth_error"
    assert "authentication incomplete" in kwargs["message"]


@pytest.mark.asyncio
async def test_handle_requires_expo_token(fake_event_stream, monkeypatch):
    handler = _make_handler(fake_event_stream)
    handler._send_error_event = AsyncMock()

    credential = SimpleNamespace(
        auth_state=AppleAuthStateEnum.AUTHENTICATED.value,
        apple_id="apple@example.com",
        selected_team_id="TEAM1",
    )
    monkeypatch.setattr(
        "ii_agent.realtime.socket.command.submit_testflight_handler.AppleCredentials.get_active_session",
        AsyncMock(return_value=credential),
    )
    monkeypatch.setattr(
        "ii_agent.realtime.socket.command.submit_testflight_handler.AppleCredentials.get_decrypted_session_data",
        lambda cred: {"_temp_password": "pw"},
    )
    monkeypatch.setattr(
        "ii_agent.realtime.socket.command.submit_testflight_handler.AppleCredentials.get_decrypted_expo_token",
        lambda cred: "",
    )
    monkeypatch.setattr(
        "ii_agent.realtime.socket.command.submit_testflight_handler.AppleCredentials.clear_session_password",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "ii_agent.realtime.socket.command.submit_testflight_handler.AppleCredentials.get_decrypted_app_specific_password",
        lambda cred: "app-pass",
    )

    await handler.handle({}, _session_info())

    kwargs = handler._send_error_event.await_args.kwargs
    assert kwargs["error_type"] == "validation_error"
    assert "Expo token is required" in kwargs["message"]


@pytest.mark.asyncio
async def test_handle_sandbox_missing_path(fake_event_stream, monkeypatch):
    handler = _make_handler(fake_event_stream)
    handler._send_error_event = AsyncMock()
    handler._send_testflight_log = AsyncMock()
    handler._get_sandbox_url_and_manager = AsyncMock(return_value=(None, None))

    credential = SimpleNamespace(
        auth_state=AppleAuthStateEnum.AUTHENTICATED.value,
        apple_id="apple@example.com",
        selected_team_id="TEAM1",
    )
    monkeypatch.setattr(
        "ii_agent.realtime.socket.command.submit_testflight_handler.AppleCredentials.get_active_session",
        AsyncMock(return_value=credential),
    )
    monkeypatch.setattr(
        "ii_agent.realtime.socket.command.submit_testflight_handler.AppleCredentials.get_decrypted_session_data",
        lambda cred: {"_temp_password": "pw"},
    )
    monkeypatch.setattr(
        "ii_agent.realtime.socket.command.submit_testflight_handler.AppleCredentials.get_decrypted_expo_token",
        lambda cred: "expo-token",
    )
    monkeypatch.setattr(
        "ii_agent.realtime.socket.command.submit_testflight_handler.AppleCredentials.clear_session_password",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "ii_agent.realtime.socket.command.submit_testflight_handler.AppleCredentials.get_decrypted_app_specific_password",
        lambda cred: "app-pass",
    )

    await handler.handle({}, _session_info())

    handler._send_testflight_log.assert_awaited()
    kwargs = handler._send_error_event.await_args.kwargs
    assert kwargs["error_type"] == "sandbox_error"
    assert "No sandbox found" in kwargs["message"]


def test_extract_tool_output_handles_structured_and_text_fallback(fake_event_stream):
    handler = _make_handler(fake_event_stream)

    as_text = handler._extract_tool_output(
        SimpleNamespace(
            structured_content={"user_display_content": "line-1"},
            content=[],
        )
    )
    assert as_text == "line-1"

    as_joined = handler._extract_tool_output(
        SimpleNamespace(
            structured_content={},
            content=[SimpleNamespace(text="a"), SimpleNamespace(text="b")],
        )
    )
    assert as_joined == "a\nb"


@pytest.mark.asyncio
async def test_get_sandbox_url_and_manager_paths(fake_event_stream, monkeypatch):
    handler = _make_handler(fake_event_stream)
    handler.container.sandbox_service.resolve_sandbox_for_session = AsyncMock(return_value=None)

    class _DBCM:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "ii_agent.realtime.socket.command.submit_testflight_handler.get_db_session_local",
        lambda: _DBCM(),
    )

    url, manager = await handler._get_sandbox_url_and_manager(_session_info())
    assert url is None and manager is None

    sandbox_record = SimpleNamespace(
        id="sid",
        session_id="session-1",
        provider_sandbox_id="provider-1",
    )
    handler.container.sandbox_service.resolve_sandbox_for_session = AsyncMock(
        return_value=sandbox_record
    )
    fake_manager = SimpleNamespace(expose_port=AsyncMock(return_value="https://sandbox.local"))
    monkeypatch.setattr(
        "ii_agent.realtime.socket.command.submit_testflight_handler.E2BSandboxManager.connect",
        AsyncMock(return_value=fake_manager),
    )

    url, manager = await handler._get_sandbox_url_and_manager(_session_info())
    assert url == "https://sandbox.local"
    assert manager is fake_manager


@pytest.mark.asyncio
async def test_get_project_path_and_send_log_event(fake_event_stream, monkeypatch):
    handler = _make_handler(fake_event_stream)

    class _DBCM:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "ii_agent.realtime.socket.command.submit_testflight_handler.get_db_session_local",
        lambda: _DBCM(),
    )
    handler.container.project_service.get_session_project_or_none = AsyncMock(
        return_value=SimpleNamespace(project_path="/workspace/app"),
    )

    path = await handler._get_project_path(_session_info())
    assert path == "/workspace/app"

    await handler._send_testflight_log(str(uuid4()), "hello", status="running")
    assert fake_event_stream.published
    event = fake_event_stream.published[-1]
    assert event.type == EventType.TESTFLIGHT_LOG
    assert event.content["message"] == "hello"
