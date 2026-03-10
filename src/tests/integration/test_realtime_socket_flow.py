from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ii_agent.agent.socket.socketio import SocketIOManager

pytestmark = pytest.mark.integration


class FakeSio:
    def __init__(self):
        self.sessions = {}
        self.events = []
        self.rooms = []

    async def save_session(self, sid, data):
        self.sessions[sid] = data

    async def get_session(self, sid):
        return self.sessions.get(sid)

    async def emit(self, event, payload, room=None):
        self.events.append((event, payload, room))

    async def enter_room(self, sid, room):
        self.rooms.append((sid, room))

    async def leave_room(self, sid, room):
        return None

    async def disconnect(self, sid):
        return None

    def event(self, fn):
        return fn

    def on(self, name):
        def _decorator(fn):
            return fn

        return _decorator


@pytest.mark.asyncio
async def test_realtime_connect_and_join_flow(monkeypatch):
    sio = FakeSio()
    manager = SocketIOManager(sio)

    manager.command_factory = SimpleNamespace(get_handler_by_string=lambda _: None)
    session_id = uuid4()

    async def _get_or_create_session(db, session_uuid, user_id, api_version):
        return SimpleNamespace(id=session_id, user_id=user_id)

    container = SimpleNamespace(
        session_service=SimpleNamespace(get_or_create_session=_get_or_create_session)
    )
    manager._container = container

    @asynccontextmanager
    async def _db_cm():
        yield None

    monkeypatch.setattr("ii_agent.agent.socket.socketio.get_db_session_local", _db_cm)
    monkeypatch.setattr("ii_agent.agent.socket.socketio.jwt_handler.verify_access_token", lambda token: {"user_id": "u1"})

    connected = await manager.connect("sid-1", {}, auth={"token": "ok"})
    await manager.join_session("sid-1", {"session_uuid": str(session_id)})

    assert connected is True
    assert ("sid-1", str(session_id)) in sio.rooms
