from datetime import datetime, timezone
from uuid import uuid4

import pytest

from ii_agent.realtime.events.models import EventType, RealtimeEvent
from ii_agent.realtime.events.service import EventService


class FakeEventRepo:
    def __init__(self):
        self.saved = []

    async def save(self, db, session_id, event, created_at=None):
        self.saved.append((db, session_id, event, created_at))
        return {"ok": True, "created_at": created_at}


@pytest.mark.asyncio
async def test_normalize_timestamp_uses_event_timestamp_when_present(settings_factory):
    service = EventService(event_repo=FakeEventRepo(), config=settings_factory())
    now = datetime(2026, 2, 1, tzinfo=timezone.utc).timestamp()

    event = RealtimeEvent(type=EventType.SYSTEM, content={"x": 1}, timestamp=now)
    normalized = service._normalize_timestamp(event)

    assert normalized == datetime.fromtimestamp(now, tz=timezone.utc)


@pytest.mark.asyncio
async def test_save_event_delegates_to_repository_with_utc_timestamp(settings_factory):
    repo = FakeEventRepo()
    service = EventService(event_repo=repo, config=settings_factory())

    event = RealtimeEvent(type=EventType.SYSTEM, content={"message": "hi"})
    session_id = uuid4()

    result = await service.save_event(db=None, session_id=session_id, event=event)

    assert result["ok"] is True
    assert repo.saved[0][1] == session_id
    assert repo.saved[0][3].tzinfo == timezone.utc
