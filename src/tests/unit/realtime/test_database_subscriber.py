from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from ii_agent.realtime.events.models import EventType, RealtimeEvent
from ii_agent.realtime.subscribers.database_subscriber import DatabaseSubscriber


@pytest.mark.asyncio
async def test_database_subscriber_skips_ignored_event_types(monkeypatch):
    container = SimpleNamespace(file_service=SimpleNamespace())
    subscriber = DatabaseSubscriber(container=container)

    save_called = {"count": 0}

    async def _fake_save(self, db, session_id, event):
        save_called["count"] += 1

    @asynccontextmanager
    async def _db_cm():
        yield None

    monkeypatch.setattr("ii_agent.realtime.subscribers.database_subscriber.get_db_session_local", _db_cm)
    monkeypatch.setattr("ii_agent.realtime.subscribers.database_subscriber.EventRepository.save", _fake_save)

    event = RealtimeEvent(type=EventType.USER_MESSAGE, session_id=uuid4(), content={"text": "hi"})
    await subscriber.handle_event(event)

    assert save_called["count"] == 0


@pytest.mark.asyncio
async def test_database_subscriber_converts_file_url_tool_result(monkeypatch):
    async def _write_file_from_url(**kwargs):
        return SimpleNamespace(id="file-1", storage_path="users/u1/file.png")

    container = SimpleNamespace(
        file_service=SimpleNamespace(write_file_from_url=_write_file_from_url)
    )
    subscriber = DatabaseSubscriber(container=container)

    saved = []

    async def _fake_save(self, db, session_id, event):
        saved.append(event)

    @asynccontextmanager
    async def _db_cm():
        yield None

    monkeypatch.setattr("ii_agent.realtime.subscribers.database_subscriber.get_db_session_local", _db_cm)
    monkeypatch.setattr("ii_agent.realtime.subscribers.database_subscriber.EventRepository.save", _fake_save)

    event = RealtimeEvent(
        type=EventType.TOOL_RESULT,
        session_id=uuid4(),
        content={
            "tool_name": "generate_image",
            "result": {
                "type": "file_url",
                "url": "https://cdn/image.png",
                "name": "image.png",
                "size": 123,
                "mime_type": "image/png",
            },
        },
    )

    await subscriber.handle_event(event)

    assert saved
    assert event.content["result"]["file_id"] == "file-1"
    assert event.content["result"]["file_storage_path"] == "users/u1/file.png"


@pytest.mark.asyncio
async def test_database_subscriber_ignores_integrity_errors(monkeypatch):
    container = SimpleNamespace(file_service=SimpleNamespace())
    subscriber = DatabaseSubscriber(container=container)

    async def _raise_integrity(self, db, session_id, event):
        raise IntegrityError("stmt", "params", Exception("duplicate"))

    @asynccontextmanager
    async def _db_cm():
        yield None

    monkeypatch.setattr("ii_agent.realtime.subscribers.database_subscriber.get_db_session_local", _db_cm)
    monkeypatch.setattr("ii_agent.realtime.subscribers.database_subscriber.EventRepository.save", _raise_integrity)

    event = RealtimeEvent(type=EventType.SYSTEM, session_id=uuid4(), content={"message": "ok"})

    await subscriber.handle_event(event)
