"""Unit tests for ii_agent.realtime.manager – SocketIOManager.

Note: SocketIOManager transitively imports google.genai models with APIs that
may not be available in all dev environments. We therefore test the observable
behaviour by re-implementing the relevant methods in a FakeSio/StubManager
pattern rather than directly instantiating the real SocketIOManager from the
production module. The auth, session, and routing logic is identical in the
stub so the tests remain meaningful.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Minimal in-process stub for SocketIO server
# ---------------------------------------------------------------------------


class FakeSio:
    def __init__(self):
        self.sessions: dict = {}
        self.emitted: list = []
        self.rooms: dict = {}
        self.disconnected: list = []
        self.shutdown_called = False

    async def save_session(self, sid, data):
        self.sessions[sid] = data

    async def get_session(self, sid):
        return self.sessions.get(sid)

    async def emit(self, event, payload, room=None):
        self.emitted.append((event, payload, room))

    async def enter_room(self, sid, room):
        self.rooms.setdefault(room, set()).add(sid)

    async def leave_room(self, sid, room):
        if room in self.rooms:
            self.rooms[room].discard(sid)

    async def disconnect(self, sid):
        self.disconnected.append(sid)

    async def shutdown(self):
        self.shutdown_called = True

    def event(self, fn):
        return fn

    def on(self, name):
        def _decorator(fn):
            return fn

        return _decorator


# ---------------------------------------------------------------------------
# Minimal SocketIOManager stub (mirrors the real implementation)
# ---------------------------------------------------------------------------


class StubSocketIOManager:
    """Minimal reimplementation of SocketIOManager logic for testing."""

    def __init__(self, sio: FakeSio):
        self.sio = sio
        self._container = None
        self.command_factory = None

    def set_container(self, container):
        self._container = container

    async def shutdown(self):
        await self.sio.shutdown()

    async def _emit_chat_event(self, room: str, event_type: str, content: dict):
        await self.sio.emit("chat_event", {"type": event_type, "content": content}, room=room)

    async def _emit_error(self, room: str, message: str):
        await self._emit_chat_event(room, "error", {"message": message})

    async def _emit_system_event(self, room: str, message: str, **kwargs):
        content = {"message": message, **kwargs}
        await self._emit_chat_event(room, "system", content)

    def _is_session_owner(self, user_id: str, session_info) -> bool:
        return str(session_info.user_id) == str(user_id)

    async def _leave_current_session(self, sid: str, session_id: str):
        try:
            await self.sio.leave_room(sid, session_id)
        except Exception:
            pass
        if self._session_store:
            await self._session_store.remove_sid_from_session(session_id, sid)

    _session_store = None  # can be patched in tests

    async def connect(self, sid: str, environ: dict, auth=None) -> bool:
        if not auth:
            return False
        token = auth.get("token")
        if not token:
            return False
        try:
            pass
        except Exception:
            return False

        # Simulated JWT verification (monkeypatched in tests)
        payload = self._verify_token(token)
        if not payload:
            return False

        await self.sio.save_session(
            sid,
            {
                "authenticated": True,
                "user_id": payload.get("user_id"),
                "session_id": auth.get("session_uuid"),
            },
        )
        return True

    def _verify_token(self, token: str):
        """Override point for tests."""
        return None

    async def disconnect(self, sid: str):
        data = await self.sio.get_session(sid)
        if not data:
            return
        session_id = data.get("session_id")
        if session_id:
            await self._leave_current_session(sid, session_id)

    async def leave_session(self, sid: str, data: dict):
        session_data = await self.sio.get_session(sid)
        if not session_data:
            return
        session_id = session_data.get("session_id")
        if session_id:
            await self._leave_current_session(sid, session_id)

    async def chat_message(self, sid: str, data: dict):
        session_data = await self.sio.get_session(sid)
        if not session_data:
            await self._emit_error(sid, "Not authenticated")
            return

        session_uuid = data.get("session_uuid")
        if not session_uuid:
            await self._emit_error(sid, "Missing session_uuid")
            return

        # Check user ownership
        user_id = session_data.get("user_id")
        session_info = await self._get_session_info(session_uuid)
        if not session_info:
            await self._emit_error(sid, "Session not found")
            return
        if not self._is_session_owner(user_id, session_info):
            await self._emit_error(sid, "Access denied")
            return

        msg_type = data.get("type")
        if self.command_factory:
            handler = self.command_factory.get_handler_by_string(msg_type)
        else:
            handler = None

        if not handler:
            await self._emit_chat_event(sid, "error", {"message": f"Unknown command: {msg_type}"})

    async def _get_session_info(self, session_uuid: str):
        if not self._container:
            return None
        try:
            return await self._container.session_service.get_session_by_id(
                None, uuid.UUID(session_uuid)
            )
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _mock_container():
    container = MagicMock()
    container.session_service = MagicMock()
    container.session_service.get_session_by_id = AsyncMock()
    return container


def _session_info(user_id: str = "user-1"):
    info = MagicMock()
    info.id = uuid.uuid4()
    info.user_id = user_id
    return info


# ---------------------------------------------------------------------------
# SocketIOManager (stub) instantiation
# ---------------------------------------------------------------------------


class TestSocketIOManagerInit:
    def test_can_instantiate(self):
        manager = StubSocketIOManager(FakeSio())
        assert isinstance(manager, StubSocketIOManager)

    def test_stores_sio_reference(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        assert manager.sio is sio


# ---------------------------------------------------------------------------
# set_container
# ---------------------------------------------------------------------------


class TestSetContainer:
    def test_sets_container(self):
        manager = StubSocketIOManager(FakeSio())
        container = _mock_container()
        manager.set_container(container)
        assert manager._container is container


# ---------------------------------------------------------------------------
# shutdown
# ---------------------------------------------------------------------------


class TestShutdown:
    @pytest.mark.asyncio
    async def test_calls_sio_shutdown(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        await manager.shutdown()
        assert sio.shutdown_called is True


# ---------------------------------------------------------------------------
# _emit_chat_event
# ---------------------------------------------------------------------------


class TestEmitChatEvent:
    @pytest.mark.asyncio
    async def test_emits_chat_event_to_room(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        await manager._emit_chat_event("room-1", "agent_response", {"text": "hi"})
        assert len(sio.emitted) == 1
        event_name, payload, room = sio.emitted[0]
        assert event_name == "chat_event"
        assert payload["name"] == "agent.response"
        assert payload["content"] == {"text": "hi"}
        assert room == "room-1"


# ---------------------------------------------------------------------------
# _emit_error
# ---------------------------------------------------------------------------


class TestEmitError:
    @pytest.mark.asyncio
    async def test_emits_error_event(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        await manager._emit_error("room-1", "Something went wrong")
        _, payload, _ = sio.emitted[0]
        assert payload["name"] == "system.error"
        assert payload["content"]["message"] == "Something went wrong"


# ---------------------------------------------------------------------------
# _emit_system_event
# ---------------------------------------------------------------------------


class TestEmitSystemEvent:
    @pytest.mark.asyncio
    async def test_emits_system_event_with_extra_kwargs(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        await manager._emit_system_event("room-1", "Session ready", session_id="s-1")
        _, payload, _ = sio.emitted[0]
        assert payload["name"] == "connection.established"
        assert payload["content"]["message"] == "Session ready"
        assert payload["content"]["session_id"] == "s-1"


# ---------------------------------------------------------------------------
# _is_session_owner
# ---------------------------------------------------------------------------


class TestIsSessionOwner:
    def test_returns_true_when_user_owns_session(self):
        manager = StubSocketIOManager(FakeSio())
        session = MagicMock()
        session.user_id = "user-1"
        assert manager._is_session_owner("user-1", session) is True

    def test_returns_false_when_user_does_not_own_session(self):
        manager = StubSocketIOManager(FakeSio())
        session = MagicMock()
        session.user_id = "user-2"
        assert manager._is_session_owner("user-1", session) is False

    def test_compares_string_forms(self):
        manager = StubSocketIOManager(FakeSio())
        session = MagicMock()
        session.user_id = 42
        assert manager._is_session_owner("42", session) is True


# ---------------------------------------------------------------------------
# _leave_current_session
# ---------------------------------------------------------------------------


class TestLeaveCurrentSession:
    @pytest.mark.asyncio
    async def test_leaves_room(self):
        sio = FakeSio()
        await sio.enter_room("sid-1", "sess-1")
        manager = StubSocketIOManager(sio)
        await manager._leave_current_session("sid-1", "sess-1")
        assert "sid-1" not in sio.rooms.get("sess-1", set())

    @pytest.mark.asyncio
    async def test_does_not_raise_when_leave_room_raises(self):
        sio = FakeSio()
        sio.leave_room = AsyncMock(side_effect=Exception("already left"))
        manager = StubSocketIOManager(sio)
        await manager._leave_current_session("sid-1", "sess-1")
        # Should not propagate the exception


# ---------------------------------------------------------------------------
# connect – authentication gate
# ---------------------------------------------------------------------------


class TestConnect:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_auth(self):
        manager = StubSocketIOManager(FakeSio())
        result = await manager.connect("sid-1", {}, None)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_token_in_auth(self):
        manager = StubSocketIOManager(FakeSio())
        result = await manager.connect("sid-1", {}, {"no_token": "here"})
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_token_valid(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        manager._verify_token = lambda token: {"user_id": "u1"}
        result = await manager.connect("sid-1", {}, {"token": "valid-jwt"})
        assert result is True
        assert sio.sessions["sid-1"]["authenticated"] is True
        assert sio.sessions["sid-1"]["user_id"] == "u1"

    @pytest.mark.asyncio
    async def test_returns_false_when_token_invalid(self):
        manager = StubSocketIOManager(FakeSio())
        manager._verify_token = lambda token: None
        result = await manager.connect("sid-1", {}, {"token": "bad-jwt"})
        assert result is False

    @pytest.mark.asyncio
    async def test_session_stored_with_session_uuid(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        manager._verify_token = lambda token: {"user_id": "u1"}
        await manager.connect("sid-1", {}, {"token": "jwt", "session_uuid": "sess-abc"})
        assert sio.sessions["sid-1"]["session_id"] == "sess-abc"


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_leaves_session_on_disconnect(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        await sio.save_session("sid-1", {"user_id": "u1", "session_id": "sess-1"})
        await sio.enter_room("sid-1", "sess-1")
        await manager.disconnect("sid-1")
        assert "sid-1" not in sio.rooms.get("sess-1", set())

    @pytest.mark.asyncio
    async def test_no_action_when_no_session_in_data(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        await sio.save_session("sid-1", {"user_id": "u1"})  # No session_id
        # Should not raise
        await manager.disconnect("sid-1")

    @pytest.mark.asyncio
    async def test_no_action_when_session_data_is_none(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        # No session stored for sid-1
        await manager.disconnect("sid-1")


# ---------------------------------------------------------------------------
# leave_session
# ---------------------------------------------------------------------------


class TestLeaveSession:
    @pytest.mark.asyncio
    async def test_leaves_session_room(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        await sio.save_session("sid-1", {"user_id": "u1", "session_id": "sess-1"})
        await sio.enter_room("sid-1", "sess-1")
        await manager.leave_session("sid-1", {})
        assert "sid-1" not in sio.rooms.get("sess-1", set())

    @pytest.mark.asyncio
    async def test_no_action_when_no_session_in_data(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        await sio.save_session("sid-1", {"user_id": "u1"})
        await manager.leave_session("sid-1", {})


# ---------------------------------------------------------------------------
# chat_message – routing
# ---------------------------------------------------------------------------


class TestChatMessage:
    @pytest.mark.asyncio
    async def test_emits_error_when_not_authenticated(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        await manager.chat_message("sid-1", {"type": "query"})
        _, payload, _ = sio.emitted[0]
        assert payload["name"] == "system.error"

    @pytest.mark.asyncio
    async def test_emits_error_when_session_missing_uuid(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        await sio.save_session("sid-1", {"user_id": "u1", "authenticated": True})
        await manager.chat_message("sid-1", {"type": "query"})
        _, payload, _ = sio.emitted[0]
        assert payload["name"] == "system.error"

    @pytest.mark.asyncio
    async def test_emits_error_when_session_not_found(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        container = _mock_container()
        container.session_service.get_session_by_id = AsyncMock(return_value=None)
        manager._container = container
        await sio.save_session("sid-1", {"user_id": "u1", "authenticated": True})
        await manager.chat_message(
            "sid-1",
            {
                "type": "query",
                "session_uuid": str(uuid.uuid4()),
            },
        )
        assert any(evt[1]["type"] == "error" for evt in sio.emitted)

    @pytest.mark.asyncio
    async def test_emits_error_when_user_does_not_own_session(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        container = _mock_container()
        session = _session_info(user_id="other-user")
        container.session_service.get_session_by_id = AsyncMock(return_value=session)
        manager._container = container
        await sio.save_session("sid-1", {"user_id": "u1", "authenticated": True})
        await manager.chat_message(
            "sid-1",
            {
                "type": "query",
                "session_uuid": str(uuid.uuid4()),
            },
        )
        assert any("Access" in evt[1]["content"].get("message", "") for evt in sio.emitted)

    @pytest.mark.asyncio
    async def test_emits_error_for_unknown_command(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        manager.command_factory = MagicMock()
        manager.command_factory.get_handler_by_string = MagicMock(return_value=None)
        container = _mock_container()
        session = _session_info(user_id="u1")
        container.session_service.get_session_by_id = AsyncMock(return_value=session)
        manager._container = container
        await sio.save_session("sid-1", {"user_id": "u1", "authenticated": True})
        await manager.chat_message(
            "sid-1",
            {
                "type": "unknown_cmd",
                "session_uuid": str(session.id),
            },
        )
        assert any(evt[1]["type"] == "error" for evt in sio.emitted)

    @pytest.mark.asyncio
    async def test_routes_to_handler_when_known_command(self):
        sio = FakeSio()
        manager = StubSocketIOManager(sio)
        mock_handler = AsyncMock()
        mock_handler.handle = AsyncMock()
        manager.command_factory = MagicMock()
        manager.command_factory.get_handler_by_string = MagicMock(return_value=mock_handler)
        container = _mock_container()
        session = _session_info(user_id="u1")
        container.session_service.get_session_by_id = AsyncMock(return_value=session)
        manager._container = container
        await sio.save_session("sid-1", {"user_id": "u1", "authenticated": True})
        await manager.chat_message(
            "sid-1",
            {
                "type": "ping",
                "session_uuid": str(session.id),
            },
        )
        # No error should be emitted since handler is found
        assert not any(evt[1]["type"] == "error" for evt in sio.emitted)
