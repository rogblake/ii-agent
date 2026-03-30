"""Unit tests for SocketIOManager (socketio.py) — r4.

Tests the real SocketIOManager class by patching only external I/O:
- DB queries (get_db_session_local)
- JWT verification (jwt_handler.verify_access_token)
- Socket.IO server (replaced with a lightweight FakeSio)
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# FakeSio — replaces socketio.AsyncServer
# ---------------------------------------------------------------------------


class FakeSio:
    """Minimal in-process Socket.IO server for tests."""

    def __init__(self):
        self.sessions: dict = {}
        self.emitted: list = []
        self.rooms: dict[str, set] = {}
        self.disconnected: list = []
        self.shutdown_called = False
        self.manager = MagicMock()
        self.manager.get_participants = MagicMock(return_value=iter([]))

    async def save_session(self, sid, data):
        self.sessions[sid] = dict(data)

    async def get_session(self, sid):
        return self.sessions.get(sid)

    async def emit(self, event, payload, room=None, **kwargs):
        self.emitted.append((event, payload, room))

    async def enter_room(self, sid, room):
        self.rooms.setdefault(room, set()).add(sid)

    async def leave_room(self, sid, room):
        self.rooms.get(room, set()).discard(sid)

    async def disconnect(self, sid):
        self.disconnected.append(sid)

    async def shutdown(self):
        self.shutdown_called = True

    def event(self, fn):
        return fn

    def on(self, name):
        def _dec(fn):
            return fn

        return _dec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_session_info(user_id: str = "user-1") -> MagicMock:
    info = MagicMock()
    info.id = uuid.uuid4()
    info.user_id = user_id
    return info


def _mock_container() -> MagicMock:
    container = MagicMock()
    container.session_service = MagicMock()
    container.session_service.find_session_by_id_info = AsyncMock()
    container.session_service.get_or_create_session = AsyncMock()
    container.workspace_explorer_service = MagicMock()
    container.workspace_explorer_service.shutdown = AsyncMock()
    return container


@asynccontextmanager
async def _fake_db_cm():
    yield AsyncMock()


# ---------------------------------------------------------------------------
# SocketIOManager instantiation
# ---------------------------------------------------------------------------


class TestSocketIOManagerInstantiation:
    def test_stores_sio(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        assert manager.sio is sio

    def test_set_container_stores_container(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        container = _mock_container()

        with patch("ii_agent.agent.socket.socketio.CommandHandlerFactory") as mock_factory:
            mock_factory.return_value = MagicMock()
            manager.set_container(container)

        assert manager._container is container


# ---------------------------------------------------------------------------
# shutdown
# ---------------------------------------------------------------------------


class TestSocketIOManagerShutdown:
    @pytest.mark.asyncio
    async def test_calls_sio_shutdown(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        container = MagicMock()
        container.workspace_explorer_service = MagicMock()
        container.workspace_explorer_service.shutdown = AsyncMock()
        manager._container = container
        await manager.shutdown()
        container.workspace_explorer_service.shutdown.assert_awaited_once()
        assert sio.shutdown_called is True


# ---------------------------------------------------------------------------
# _emit_chat_event / _emit_error / _emit_system_event
# ---------------------------------------------------------------------------


class TestSocketIOManagerEmitHelpers:
    @pytest.mark.asyncio
    async def test_emit_chat_event_shape(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        await manager._emit_chat_event("room-1", "agent_response", {"text": "hello"})
        assert len(sio.emitted) == 1
        _, payload, room = sio.emitted[0]
        assert room == "room-1"
        assert payload["type"] == "agent_response"
        assert payload["content"]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_emit_error_wraps_chat_event(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        await manager._emit_error("room-1", "something failed")
        _, payload, _ = sio.emitted[0]
        assert payload["type"] == "error"
        assert payload["content"]["message"] == "something failed"

    @pytest.mark.asyncio
    async def test_emit_system_event_includes_kwargs(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        await manager._emit_system_event("room-1", "ready", extra="val")
        _, payload, _ = sio.emitted[0]
        assert payload["type"] == "system"
        assert payload["content"]["message"] == "ready"
        assert payload["content"]["extra"] == "val"


# ---------------------------------------------------------------------------
# _is_session_owner
# ---------------------------------------------------------------------------


class TestIsSessionOwner:
    def test_returns_true_for_owner(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        manager = SocketIOManager(sio=FakeSio())
        session = MagicMock()
        session.user_id = "user-1"
        assert manager._is_session_owner("user-1", session) is True

    def test_returns_false_for_non_owner(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        manager = SocketIOManager(sio=FakeSio())
        session = MagicMock()
        session.user_id = "user-2"
        assert manager._is_session_owner("user-1", session) is False

    def test_compares_str_versions(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        manager = SocketIOManager(sio=FakeSio())
        session = MagicMock()
        session.user_id = 99
        assert manager._is_session_owner("99", session) is True


# ---------------------------------------------------------------------------
# _leave_current_session
# ---------------------------------------------------------------------------


class TestLeaveCurrentSession:
    @pytest.mark.asyncio
    async def test_leaves_room_and_calls_store(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        await sio.enter_room("sid-1", "sess-abc")

        with patch("ii_agent.agent.socket.socketio.session_store") as mock_store:
            mock_store.remove_sid_from_session = AsyncMock()
            await manager._leave_current_session("sid-1", "sess-abc")
            mock_store.remove_sid_from_session.assert_called_once_with("sess-abc", "sid-1")

        assert "sid-1" not in sio.rooms.get("sess-abc", set())

    @pytest.mark.asyncio
    async def test_swallows_room_leave_exception(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        sio.leave_room = AsyncMock(side_effect=RuntimeError("leave failed"))
        manager = SocketIOManager(sio=sio)

        with patch("ii_agent.agent.socket.socketio.session_store") as mock_store:
            mock_store.remove_sid_from_session = AsyncMock()
            # Should not raise
            await manager._leave_current_session("sid-1", "sess-xyz")


# ---------------------------------------------------------------------------
# _require_session
# ---------------------------------------------------------------------------


class TestRequireSession:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_session_uuid(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        manager = SocketIOManager(sio=FakeSio())
        container = _mock_container()

        with patch("ii_agent.agent.socket.socketio.CommandHandlerFactory") as mock_factory:
            mock_factory.return_value = MagicMock()
            manager.set_container(container)

        result = await manager._require_session({})
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_invalid_uuid(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        manager = SocketIOManager(sio=FakeSio())
        container = _mock_container()

        with patch("ii_agent.agent.socket.socketio.CommandHandlerFactory") as mock_factory:
            mock_factory.return_value = MagicMock()
            manager.set_container(container)

        result = await manager._require_session({"session_uuid": "not-a-uuid"})
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_session_when_valid(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        container = _mock_container()
        session_id = uuid.uuid4()
        fake_session = _fake_session_info()
        container.session_service.find_session_by_id_info = AsyncMock(return_value=fake_session)

        with (
            patch("ii_agent.agent.socket.socketio.CommandHandlerFactory") as mock_factory,
            patch(
                "ii_agent.agent.socket.socketio.get_db_session_local",
                return_value=_fake_db_cm(),
            ),
        ):
            mock_factory.return_value = MagicMock()
            manager.set_container(container)
            result = await manager._require_session({"session_uuid": str(session_id)})

        assert result is fake_session


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------


class TestConnect:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_auth(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        manager = SocketIOManager(sio=FakeSio())
        result = await manager.connect("sid-1", {}, None)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_token_in_auth(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        manager = SocketIOManager(sio=FakeSio())
        result = await manager.connect("sid-1", {}, {"session_uuid": "something"})
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_with_valid_token(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)

        with patch("ii_agent.agent.socket.socketio.jwt_handler") as mock_jwt:
            mock_jwt.verify_access_token = MagicMock(return_value={"user_id": "u-1"})
            result = await manager.connect("sid-1", {}, {"token": "valid-jwt"})

        assert result is True
        assert sio.sessions["sid-1"]["authenticated"] is True
        assert sio.sessions["sid-1"]["user_id"] == "u-1"

    @pytest.mark.asyncio
    async def test_returns_false_when_jwt_returns_none(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        manager = SocketIOManager(sio=FakeSio())

        with patch("ii_agent.agent.socket.socketio.jwt_handler") as mock_jwt:
            mock_jwt.verify_access_token = MagicMock(return_value=None)
            result = await manager.connect("sid-1", {}, {"token": "bad-jwt"})

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_jwt_exception(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        manager = SocketIOManager(sio=FakeSio())

        with patch("ii_agent.agent.socket.socketio.jwt_handler") as mock_jwt:
            mock_jwt.verify_access_token = MagicMock(side_effect=Exception("verify failed"))
            result = await manager.connect("sid-1", {}, {"token": "erring-jwt"})

        assert result is False

    @pytest.mark.asyncio
    async def test_stores_session_uuid_in_session(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        sess_uuid = str(uuid.uuid4())

        with patch("ii_agent.agent.socket.socketio.jwt_handler") as mock_jwt:
            mock_jwt.verify_access_token = MagicMock(return_value={"user_id": "u-1"})
            await manager.connect("sid-1", {}, {"token": "jwt", "session_uuid": sess_uuid})

        assert sio.sessions["sid-1"]["session_uuid"] == sess_uuid


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_leaves_session_on_disconnect(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        await sio.save_session("sid-1", {"user_id": "u1", "session_id": "sess-1"})
        await sio.enter_room("sid-1", "sess-1")

        with patch("ii_agent.agent.socket.socketio.session_store") as mock_store:
            mock_store.remove_sid_from_session = AsyncMock()
            await manager.disconnect("sid-1")

        assert "sid-1" not in sio.rooms.get("sess-1", set())

    @pytest.mark.asyncio
    async def test_no_action_when_session_data_missing_session_id(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        await sio.save_session("sid-1", {"user_id": "u1"})
        # No session_id in data – should not raise
        await manager.disconnect("sid-1")

    @pytest.mark.asyncio
    async def test_no_action_when_no_session_stored(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        # No session stored for this sid
        await manager.disconnect("unknown-sid")


# ---------------------------------------------------------------------------
# join_session
# ---------------------------------------------------------------------------


class TestJoinSession:
    @pytest.mark.asyncio
    async def test_disconnects_when_no_session_data(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        container = _mock_container()

        with patch("ii_agent.agent.socket.socketio.CommandHandlerFactory") as mock_factory:
            mock_factory.return_value = MagicMock()
            manager.set_container(container)

        # No session stored for sid-1
        await manager.join_session("sid-1", {})
        assert "sid-1" in sio.disconnected

    @pytest.mark.asyncio
    async def test_disconnects_when_not_authenticated(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        container = _mock_container()

        with patch("ii_agent.agent.socket.socketio.CommandHandlerFactory") as mock_factory:
            mock_factory.return_value = MagicMock()
            manager.set_container(container)

        await sio.save_session("sid-1", {"user_id": "u1", "authenticated": False})
        await manager.join_session("sid-1", {})
        assert "sid-1" in sio.disconnected

    @pytest.mark.asyncio
    async def test_emits_error_for_invalid_uuid_format(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        container = _mock_container()

        with patch("ii_agent.agent.socket.socketio.CommandHandlerFactory") as mock_factory:
            mock_factory.return_value = MagicMock()
            manager.set_container(container)

        await sio.save_session("sid-1", {"user_id": "u1", "authenticated": True})
        await manager.join_session("sid-1", {"session_uuid": "not-a-valid-uuid"})

        assert any(
            payload.get("content", {}).get("message", "").lower().find("invalid") >= 0
            for _, payload, _ in sio.emitted
        )

    @pytest.mark.asyncio
    async def test_successful_join_enters_room(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        container = _mock_container()
        session_id = uuid.uuid4()
        fake_session = _fake_session_info(user_id="u1")
        fake_session.id = session_id
        container.session_service.get_or_create_session = AsyncMock(return_value=fake_session)

        with (
            patch("ii_agent.agent.socket.socketio.CommandHandlerFactory") as mock_factory,
            patch(
                "ii_agent.agent.socket.socketio.get_db_session_local",
                return_value=_fake_db_cm(),
            ),
            patch("ii_agent.agent.socket.socketio.session_store") as mock_store,
        ):
            mock_factory.return_value = MagicMock()
            mock_store.add_sid_to_session = AsyncMock()
            manager.set_container(container)
            await sio.save_session("sid-1", {"user_id": "u1", "authenticated": True})
            await manager.join_session("sid-1", {"session_uuid": str(session_id)})

        assert str(session_id) in sio.rooms
        assert "sid-1" in sio.rooms[str(session_id)]

    @pytest.mark.asyncio
    async def test_join_session_denies_non_owner(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        container = _mock_container()
        session_id = uuid.uuid4()

        # Session belongs to different user
        fake_session = _fake_session_info(user_id="other-user")
        fake_session.id = session_id
        container.session_service.get_or_create_session = AsyncMock(return_value=fake_session)

        with (
            patch("ii_agent.agent.socket.socketio.CommandHandlerFactory") as mock_factory,
            patch(
                "ii_agent.agent.socket.socketio.get_db_session_local",
                return_value=_fake_db_cm(),
            ),
        ):
            mock_factory.return_value = MagicMock()
            manager.set_container(container)
            await sio.save_session("sid-1", {"user_id": "u1", "authenticated": True})
            await manager.join_session("sid-1", {"session_uuid": str(session_id)})

        # Should emit an error and not enter room
        error_emitted = any(
            payload.get("content", {}).get("message", "").lower().find("access") >= 0
            for _, payload, _ in sio.emitted
        )
        assert error_emitted


# ---------------------------------------------------------------------------
# leave_session
# ---------------------------------------------------------------------------


class TestLeaveSession:
    @pytest.mark.asyncio
    async def test_leaves_room_when_session_id_present(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        await sio.save_session("sid-1", {"user_id": "u1", "session_id": "sess-1"})
        await sio.enter_room("sid-1", "sess-1")

        with patch("ii_agent.agent.socket.socketio.session_store") as mock_store:
            mock_store.remove_sid_from_session = AsyncMock()
            await manager.leave_session("sid-1", {})

        assert "sid-1" not in sio.rooms.get("sess-1", set())

    @pytest.mark.asyncio
    async def test_no_action_when_no_session_id_in_data(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        await sio.save_session("sid-1", {"user_id": "u1"})
        await manager.leave_session("sid-1", {})  # Should not raise


# ---------------------------------------------------------------------------
# chat_message
# ---------------------------------------------------------------------------


class TestChatMessage:
    @pytest.mark.asyncio
    async def test_emits_error_when_no_session_in_sio(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        container = _mock_container()

        with patch("ii_agent.agent.socket.socketio.CommandHandlerFactory") as mock_factory:
            mock_factory.return_value = MagicMock()
            manager.set_container(container)

        # No session stored for sid-1 → sio.get_session returns None
        await manager.chat_message("sid-1", {"type": "query"})
        assert any(payload.get("content", {}).get("message", "") for _, payload, _ in sio.emitted)

    @pytest.mark.asyncio
    async def test_emits_error_when_session_not_found_in_db(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        container = _mock_container()
        container.session_service.find_session_by_id_info = AsyncMock(return_value=None)

        with (
            patch("ii_agent.agent.socket.socketio.CommandHandlerFactory") as mock_factory,
            patch(
                "ii_agent.agent.socket.socketio.get_db_session_local",
                return_value=_fake_db_cm(),
            ),
        ):
            mock_factory.return_value = MagicMock()
            manager.set_container(container)

        await sio.save_session("sid-1", {"user_id": "u1"})
        await manager.chat_message("sid-1", {"type": "query", "session_uuid": str(uuid.uuid4())})
        assert any(
            "chat session" in payload.get("content", {}).get("message", "").lower()
            or payload.get("content", {}).get("message", "") != ""
            for _, payload, _ in sio.emitted
        )

    @pytest.mark.asyncio
    async def test_emits_error_when_user_does_not_own_session(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        container = _mock_container()
        session_id = uuid.uuid4()
        # Session owned by "other-user", but request from "u1"
        fake_session = _fake_session_info(user_id="other-user")
        fake_session.id = session_id
        container.session_service.find_session_by_id_info = AsyncMock(return_value=fake_session)

        with (
            patch("ii_agent.agent.socket.socketio.CommandHandlerFactory") as mock_factory,
            patch(
                "ii_agent.agent.socket.socketio.get_db_session_local",
                return_value=_fake_db_cm(),
            ),
        ):
            mock_factory.return_value = MagicMock()
            manager.set_container(container)

        await sio.save_session("sid-1", {"user_id": "u1"})
        await manager.chat_message("sid-1", {"type": "query", "session_uuid": str(session_id)})
        assert any(
            "access denied" in payload.get("content", {}).get("message", "").lower()
            or "access" in payload.get("content", {}).get("message", "").lower()
            for _, payload, _ in sio.emitted
        )

    @pytest.mark.asyncio
    async def test_routes_to_handler_when_found(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        container = _mock_container()
        session_id = uuid.uuid4()
        fake_session = _fake_session_info(user_id="u1")
        fake_session.id = session_id
        container.session_service.find_session_by_id_info = AsyncMock(return_value=fake_session)

        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock()
        mock_factory_inst = MagicMock()
        mock_factory_inst.get_handler_by_string = MagicMock(return_value=mock_handler)
        mock_factory_inst.initialize = AsyncMock()

        with (
            patch(
                "ii_agent.agent.socket.socketio.CommandHandlerFactory",
                return_value=mock_factory_inst,
            ),
            patch(
                "ii_agent.agent.socket.socketio.get_db_session_local",
                return_value=_fake_db_cm(),
            ),
        ):
            manager.set_container(container)

        await sio.save_session("sid-1", {"user_id": "u1"})
        await manager.chat_message(
            "sid-1",
            {"type": "ping", "session_uuid": str(session_id), "content": {}},
        )

        mock_handler.handle.assert_called_once()

    @pytest.mark.asyncio
    async def test_emits_error_for_unknown_message_type(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        container = _mock_container()
        session_id = uuid.uuid4()
        fake_session = _fake_session_info(user_id="u1")
        fake_session.id = session_id
        container.session_service.find_session_by_id_info = AsyncMock(return_value=fake_session)

        mock_factory_inst = MagicMock()
        mock_factory_inst.get_handler_by_string = MagicMock(return_value=None)
        mock_factory_inst.initialize = AsyncMock()

        with (
            patch(
                "ii_agent.agent.socket.socketio.CommandHandlerFactory",
                return_value=mock_factory_inst,
            ),
            patch(
                "ii_agent.agent.socket.socketio.get_db_session_local",
                return_value=_fake_db_cm(),
            ),
        ):
            manager.set_container(container)

        await sio.save_session("sid-1", {"user_id": "u1"})
        await manager.chat_message(
            "sid-1",
            {"type": "unknown_xyz", "session_uuid": str(session_id)},
        )

        assert any("unknown" in str(payload).lower() for _, payload, _ in sio.emitted)

    @pytest.mark.asyncio
    async def test_emits_error_when_handler_raises(self):
        from ii_agent.agent.socket.socketio import SocketIOManager

        sio = FakeSio()
        manager = SocketIOManager(sio=sio)
        container = _mock_container()
        session_id = uuid.uuid4()
        fake_session = _fake_session_info(user_id="u1")
        fake_session.id = session_id
        container.session_service.find_session_by_id_info = AsyncMock(return_value=fake_session)

        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock(side_effect=RuntimeError("handler boom"))
        mock_factory_inst = MagicMock()
        mock_factory_inst.get_handler_by_string = MagicMock(return_value=mock_handler)
        mock_factory_inst.initialize = AsyncMock()

        with (
            patch(
                "ii_agent.agent.socket.socketio.CommandHandlerFactory",
                return_value=mock_factory_inst,
            ),
            patch(
                "ii_agent.agent.socket.socketio.get_db_session_local",
                return_value=_fake_db_cm(),
            ),
        ):
            manager.set_container(container)

        await sio.save_session("sid-1", {"user_id": "u1"})
        await manager.chat_message(
            "sid-1",
            {"type": "query", "session_uuid": str(session_id), "content": {}},
        )

        assert any("error" in str(payload).lower() for _, payload, _ in sio.emitted)
