from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ii_agent.agent.socket.socketio import SocketIOManager


class FakeSio:
    def __init__(self):
        self.sessions = {}
        self.emitted = []
        self.disconnected = []
        self.joined = []

    async def save_session(self, sid, data):
        self.sessions[sid] = data

    async def get_session(self, sid):
        return self.sessions.get(sid)

    async def emit(self, event, payload, room=None):
        self.emitted.append((event, payload, room))

    async def disconnect(self, sid):
        self.disconnected.append(sid)

    async def enter_room(self, sid, room):
        self.joined.append((sid, room))

    async def leave_room(self, sid, room):
        return None

    def event(self, fn):
        return fn

    def on(self, name):
        def _decorator(fn):
            return fn

        return _decorator

    async def shutdown(self):
        return None


@pytest.mark.asyncio
async def test_connect_rejects_missing_auth_token(monkeypatch):
    manager = SocketIOManager(FakeSio())

    accepted = await manager.connect("sid-1", {}, auth=None)

    assert accepted is False


@pytest.mark.asyncio
async def test_connect_stores_authenticated_session(monkeypatch):
    sio = FakeSio()
    manager = SocketIOManager(sio)

    monkeypatch.setattr(
        "ii_agent.agent.socket.socketio.jwt_handler.verify_access_token",
        lambda token: {"user_id": "u1"},
    )

    accepted = await manager.connect("sid-1", {}, auth={"token": "valid", "session_uuid": "s1"})

    assert accepted is True
    assert sio.sessions["sid-1"]["authenticated"] is True
    assert sio.sessions["sid-1"]["user_id"] == "u1"


@pytest.mark.asyncio
async def test_join_session_rejects_invalid_session_uuid(monkeypatch):
    sio = FakeSio()
    manager = SocketIOManager(sio)
    manager._container = SimpleNamespace(session_service=SimpleNamespace())

    await sio.save_session("sid-1", {"authenticated": True, "user_id": "u1"})

    await manager.join_session("sid-1", {"session_uuid": "not-a-uuid"})

    assert any("Invalid session UUID format" in evt[1]["content"]["message"] for evt in sio.emitted)


@pytest.mark.asyncio
async def test_chat_message_emits_unknown_message_type_error(monkeypatch):
    sio = FakeSio()
    manager = SocketIOManager(sio)
    manager.command_factory = SimpleNamespace(get_handler_by_string=lambda _: None)

    async def _find_session_by_id_info(*args, **kwargs):
        return None

    manager._container = SimpleNamespace(
        session_service=SimpleNamespace(
            find_session_by_id_info=_find_session_by_id_info
        )
    )

    @asynccontextmanager
    async def _db_cm():
        yield None

    monkeypatch.setattr("ii_agent.agent.socket.socketio.get_db_session_local", _db_cm)

    session_id = str(uuid4())

    async def _session_lookup(db, session_uuid):
        return SimpleNamespace(id=session_uuid, user_id="u1")

    manager._container.session_service.find_session_by_id_info = (
        _session_lookup
    )
    await sio.save_session("sid-1", {"user_id": "u1", "authenticated": True})

    await manager.chat_message(
        "sid-1",
        {"session_uuid": session_id, "type": "unknown", "content": {}},
    )

    assert any(evt[1]["type"] == "error" for evt in sio.emitted)
