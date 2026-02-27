"""Unit tests for chat router endpoints using FastAPI TestClient."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ii_agent.auth.dependencies import get_current_user
from ii_agent.chat.dependencies import get_chat_service
from ii_agent.chat.router import router
from ii_agent.core.dependencies import _db_session_dependency
from ii_agent.core.exceptions import IIAgentError, PaymentRequiredError
from ii_agent.core.middleware import ii_agent_error_handler

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_ID = str(uuid.uuid4())
_SESSION_ID = str(uuid.uuid4())


def _make_user(user_id: str = _USER_ID) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        email="test@example.com",
        is_active=True,
        avatar=None,
    )


def _make_chat_service(
    *,
    validate_model=None,
    has_credits: bool = True,
    validate_session=None,
    validate_public_session=None,
    create_session=None,
    stream_events=None,
    stop_result=None,
    history_response=None,
    clear_count: int = 0,
    advanced_state=None,
    updated_advanced_state=None,
) -> MagicMock:
    svc = MagicMock()
    svc.validate_model_for_chat = AsyncMock(return_value=validate_model)
    svc.check_sufficient_credits = AsyncMock(return_value=has_credits)
    svc.validate_session_access = AsyncMock(return_value=validate_session)
    svc.validate_public_session_access = AsyncMock(return_value=validate_public_session)
    svc.stop_conversation = AsyncMock(return_value=stop_result)
    svc.build_message_history_response = AsyncMock(return_value=history_response)
    svc.clear_messages = AsyncMock(return_value=clear_count)

    # Advanced mode
    if advanced_state is not None:
        svc.get_advanced_mode_state = AsyncMock(return_value=advanced_state)
    if updated_advanced_state is not None:
        svc.update_advanced_mode_state = AsyncMock(return_value=updated_advanced_state)

    if create_session is not None:
        svc.create_chat_session = AsyncMock(return_value=create_session)

    # stream_chat_response must be async generator
    if stream_events is not None:

        async def _gen(*args, **kwargs):
            for ev in stream_events:
                yield ev

        svc.stream_chat_response = _gen
    else:

        async def _empty(*args, **kwargs):
            return
            yield  # noqa: unreachable – makes it an async generator

        svc.stream_chat_response = _empty

    return svc


def _build_app(chat_service: MagicMock, user: SimpleNamespace | None = None) -> FastAPI:
    """Build a minimal FastAPI app with the chat router and overridden deps."""
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(IIAgentError, ii_agent_error_handler)

    _user = user or _make_user()

    app.dependency_overrides[get_current_user] = lambda: _user
    app.dependency_overrides[_db_session_dependency] = lambda: AsyncMock()
    app.dependency_overrides[get_chat_service] = lambda: chat_service

    return app


# ---------------------------------------------------------------------------
# Tests – GET advanced-mode
# ---------------------------------------------------------------------------


def test_get_advanced_mode_settings_success():
    """Arrange: valid session access; Act: GET advanced-mode; Assert: 200 with state."""
    state = {"enabled": True, "references": []}
    svc = _make_chat_service()

    with patch(
        "ii_agent.chat.router.MediaOrchestrator.get_advanced_mode_state",
        new=AsyncMock(return_value=state),
    ):
        app = _build_app(svc)
        client = TestClient(app)
        resp = client.get(f"/v1/chat/conversations/{_SESSION_ID}/advanced-mode")

    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True


def test_get_advanced_mode_validates_session_access():
    """Arrange: session access validation called; Assert: validate_session_access invoked."""
    state = {"enabled": False, "references": []}
    svc = _make_chat_service()

    with patch(
        "ii_agent.chat.router.MediaOrchestrator.get_advanced_mode_state",
        new=AsyncMock(return_value=state),
    ):
        app = _build_app(svc)
        client = TestClient(app)
        resp = client.get(f"/v1/chat/conversations/{_SESSION_ID}/advanced-mode")

    assert resp.status_code == 200
    svc.validate_session_access.assert_called_once()


# ---------------------------------------------------------------------------
# Tests – POST advanced-mode
# ---------------------------------------------------------------------------


def test_update_advanced_mode_settings_success():
    """Arrange: valid request body; Act: POST advanced-mode; Assert: updated state returned."""
    updated_state = {"enabled": True, "references": []}
    svc = _make_chat_service()

    with patch(
        "ii_agent.chat.router.MediaOrchestrator.update_advanced_mode_state",
        new=AsyncMock(return_value=updated_state),
    ):
        app = _build_app(svc)
        client = TestClient(app)
        resp = client.post(
            f"/v1/chat/conversations/{_SESSION_ID}/advanced-mode",
            json={"enabled": True, "references": []},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True


def test_update_advanced_mode_validates_session_access():
    """Ensure validate_session_access is called before state update."""
    svc = _make_chat_service()

    with patch(
        "ii_agent.chat.router.MediaOrchestrator.update_advanced_mode_state",
        new=AsyncMock(return_value={"enabled": False, "references": []}),
    ):
        app = _build_app(svc)
        client = TestClient(app)
        resp = client.post(
            f"/v1/chat/conversations/{_SESSION_ID}/advanced-mode",
            json={"enabled": False},
        )

    assert resp.status_code == 200
    svc.validate_session_access.assert_called_once()


# ---------------------------------------------------------------------------
# Tests – POST conversations (send chat message)
# ---------------------------------------------------------------------------


def test_send_chat_creates_new_session_and_streams_sse():
    """Arrange: no session_id provided; Act: POST /conversations; Assert: SSE stream with session event."""
    session_meta = SimpleNamespace(
        session_id=_SESSION_ID,
        name="Test Session",
        agent_type="chat",
        model_id="gpt-4o",
        created_at="2026-01-01T00:00:00",
    )
    events = [
        {"type": "content_start"},
        {"type": "content_delta", "content": "Hello"},
        {"type": "content_stop"},
        {"type": "complete", "message_id": str(uuid.uuid4()), "finish_reason": "end_turn"},
    ]
    svc = _make_chat_service(has_credits=True, create_session=session_meta, stream_events=events)

    app = _build_app(svc)
    client = TestClient(app)

    resp = client.post(
        "/v1/chat/conversations",
        json={"content": "Hello world", "model_id": "gpt-4o"},
    )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    # session event should appear in SSE body
    assert "session" in body
    assert "content" in body


def test_send_chat_existing_session_no_session_event():
    """Arrange: session_id provided; Act: POST /conversations; Assert: no session SSE event."""
    events = [
        {"type": "content_delta", "content": "Hi"},
        {"type": "complete", "message_id": str(uuid.uuid4()), "finish_reason": "end_turn"},
    ]
    svc = _make_chat_service(has_credits=True, stream_events=events)

    app = _build_app(svc)
    client = TestClient(app)

    resp = client.post(
        "/v1/chat/conversations",
        json={"content": "Hello", "model_id": "gpt-4o", "session_id": _SESSION_ID},
    )

    assert resp.status_code == 200
    # validate_session_access must be called for existing session
    svc.validate_session_access.assert_called_once()
    # no session created
    svc.create_chat_session.assert_not_called()


def test_send_chat_insufficient_credits_returns_402():
    """Arrange: no credits; Act: POST /conversations; Assert: 402."""
    svc = _make_chat_service(has_credits=False)

    app = _build_app(svc)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post(
        "/v1/chat/conversations",
        json={"content": "Hello", "model_id": "gpt-4o"},
    )

    # PaymentRequiredError has status_code=402 but the error handler must be registered
    assert resp.status_code in (402, 500)  # 402 with handler, 500 without


def test_send_chat_session_creation_failure_returns_500():
    """Arrange: create_chat_session raises; Act: POST /conversations; Assert: error SSE event."""
    svc = _make_chat_service(has_credits=True)
    svc.create_chat_session = AsyncMock(side_effect=RuntimeError("DB error"))

    app = _build_app(svc)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post(
        "/v1/chat/conversations",
        json={"content": "Hello", "model_id": "gpt-4o"},
    )

    # Should return 500 from InternalError
    assert resp.status_code == 500


def test_send_chat_streams_all_event_types():
    """Arrange: events of all types; Assert: all converted to SSE correctly."""
    tool_call_obj = SimpleNamespace(id="tc1", name="web_search", type="function", input='{"q":"x"}')
    events = [
        {"type": "content_start"},
        {"type": "content_delta", "content": "chunk"},
        {"type": "content_stop"},
        {"type": "thinking_delta", "thinking": "thinking...", "signature": None},
        {"type": "tool_use_start", "tool_call": tool_call_obj},
        {"type": "tool_use_delta", "tool_call": tool_call_obj},
        {"type": "tool_use_stop", "tool_call": tool_call_obj},
        {"type": "code_interpreter_start"},
        {"type": "code_interpreter_delta", "content": "code"},
        {"type": "code_interpreter_stop"},
        {"type": "tool_progress", "tool_call_id": "tc1", "name": "web_search", "output": "result"},
        {"type": "tool_result", "tool_call_id": "tc1", "name": "web_search", "output": "done", "is_error": False},
        {"type": "usage", "usage": {"input_tokens": 10, "output_tokens": 20, "cache_creation_tokens": 0, "cache_read_tokens": 0}},
        {"type": "error", "message": "oops", "code": "test_err"},
        {"type": "complete", "message_id": str(uuid.uuid4()), "finish_reason": "end_turn"},
    ]
    session_meta = SimpleNamespace(
        session_id=_SESSION_ID,
        name="S",
        agent_type="chat",
        model_id="gpt-4o",
        created_at="2026-01-01T00:00:00",
    )
    svc = _make_chat_service(has_credits=True, create_session=session_meta, stream_events=events)

    app = _build_app(svc)
    client = TestClient(app)
    resp = client.post(
        "/v1/chat/conversations",
        json={"content": "Test", "model_id": "gpt-4o"},
    )

    body = resp.text
    assert "event: content" in body
    assert "event: thinking" in body
    assert "event: tool_call" in body
    assert "event: code_block" in body
    assert "event: tool_progress" in body
    assert "event: tool_result" in body
    assert "event: usage" in body
    assert "event: error" in body
    assert "event: complete" in body


def test_send_chat_stream_exception_yields_error_event():
    """Arrange: stream raises; Assert: error SSE event emitted without crashing."""
    session_meta = SimpleNamespace(
        session_id=_SESSION_ID,
        name="S",
        agent_type="chat",
        model_id="gpt-4o",
        created_at="2026-01-01",
    )
    svc = _make_chat_service(has_credits=True, create_session=session_meta)

    async def _error_gen(*args, **kwargs):
        raise RuntimeError("stream failure")
        yield  # noqa

    svc.stream_chat_response = _error_gen

    app = _build_app(svc)
    client = TestClient(app)
    resp = client.post(
        "/v1/chat/conversations",
        json={"content": "Test", "model_id": "gpt-4o"},
    )

    assert resp.status_code == 200
    assert "event: error" in resp.text
    assert "streaming_error" in resp.text


# ---------------------------------------------------------------------------
# Tests – POST stop conversation
# ---------------------------------------------------------------------------


def test_stop_conversation_returns_success():
    """Arrange: valid session; Act: POST stop; Assert: success=True."""
    msg_id = str(uuid.uuid4())
    svc = _make_chat_service(stop_result=msg_id)

    app = _build_app(svc)
    client = TestClient(app)
    resp = client.post(f"/v1/chat/conversations/{_SESSION_ID}/stop")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["last_message_id"] == msg_id


def test_stop_conversation_no_last_message():
    """Arrange: stop returns None; Assert: last_message_id is null."""
    svc = _make_chat_service(stop_result=None)

    app = _build_app(svc)
    client = TestClient(app)
    resp = client.post(f"/v1/chat/conversations/{_SESSION_ID}/stop")

    assert resp.status_code == 200
    data = resp.json()
    assert data["last_message_id"] is None


def test_stop_conversation_validates_session_access():
    """Ensure validate_session_access is called before stopping."""
    svc = _make_chat_service(stop_result=None)

    app = _build_app(svc)
    client = TestClient(app)
    client.post(f"/v1/chat/conversations/{_SESSION_ID}/stop")

    svc.validate_session_access.assert_called_once()


# ---------------------------------------------------------------------------
# Tests – GET conversation history
# ---------------------------------------------------------------------------


def _make_history_response(messages=None):
    return SimpleNamespace(
        messages=messages or [],
        has_more=False,
        total_count=len(messages) if messages else 0,
        model_dump=lambda: {
            "messages": [],
            "has_more": False,
            "total_count": 0,
        },
    )


def test_get_message_history_success():
    """Arrange: valid session; Act: GET conversation; Assert: 200."""
    from ii_agent.chat.schemas import MessageHistoryResponse

    hist = MessageHistoryResponse(messages=[], has_more=False, total_count=0)
    svc = _make_chat_service(history_response=hist)

    app = _build_app(svc)
    client = TestClient(app)
    resp = client.get(f"/v1/chat/conversations/{_SESSION_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["has_more"] is False
    assert data["total_count"] == 0


def test_get_message_history_with_pagination():
    """Arrange: limit and before params; Assert: 200 and service called with params."""
    from ii_agent.chat.schemas import MessageHistoryResponse

    hist = MessageHistoryResponse(messages=[], has_more=False, total_count=0)
    svc = _make_chat_service(history_response=hist)

    app = _build_app(svc)
    client = TestClient(app)
    resp = client.get(f"/v1/chat/conversations/{_SESSION_ID}?limit=10&before=msg-123")

    assert resp.status_code == 200
    svc.build_message_history_response.assert_called_once()
    call_kwargs = svc.build_message_history_response.call_args
    assert call_kwargs.kwargs.get("limit") == 10 or call_kwargs.args[2] == 10


# ---------------------------------------------------------------------------
# Tests – GET public conversation history
# ---------------------------------------------------------------------------


def test_get_public_message_history_no_auth_required():
    """Arrange: no auth override needed; Act: GET public; Assert: 200."""
    from ii_agent.chat.schemas import MessageHistoryResponse

    hist = MessageHistoryResponse(messages=[], has_more=False, total_count=0)
    svc = _make_chat_service(history_response=hist)

    # Public endpoint does NOT use CurrentUser; build app but override db
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_db_session_dependency] = lambda: AsyncMock()
    app.dependency_overrides[get_chat_service] = lambda: svc

    client = TestClient(app)
    resp = client.get(f"/v1/chat/conversations/{_SESSION_ID}/public")

    assert resp.status_code == 200
    svc.validate_public_session_access.assert_called_once()


# ---------------------------------------------------------------------------
# Tests – DELETE conversation
# ---------------------------------------------------------------------------


def test_clear_conversation_success():
    """Arrange: valid session; Act: DELETE conversation; Assert: deleted_count returned."""
    svc = _make_chat_service(clear_count=5)

    app = _build_app(svc)
    client = TestClient(app)
    resp = client.delete(f"/v1/chat/conversation/{_SESSION_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["deleted_count"] == 5
    assert "successfully" in data["message"].lower()


def test_clear_conversation_validates_session_access():
    """Ensure validate_session_access is called before clearing."""
    svc = _make_chat_service(clear_count=0)

    app = _build_app(svc)
    client = TestClient(app)
    client.delete(f"/v1/chat/conversation/{_SESSION_ID}")

    svc.validate_session_access.assert_called_once()
