from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ii_agent.realtime.events.app_events import AgentStatusUpdateEvent
from ii_agent.realtime.pubsub.callbacks import DatabaseCallbackHandler


@pytest.mark.asyncio
async def test_database_callback_handler_serializes_nested_uuid_content(monkeypatch):
    event_repo = AsyncMock()
    handler = DatabaseCallbackHandler(event_repo=event_repo)
    db = object()

    @asynccontextmanager
    async def _db_cm():
        yield db

    monkeypatch.setattr("ii_agent.realtime.pubsub.callbacks.get_db_session_local", _db_cm)

    nested_uuid = uuid4()
    event = AgentStatusUpdateEvent(
        session_id=uuid4(),
        content={
            "operation": "design_mode_sync",
            "progress": {
                "session_id": nested_uuid,
                "processed": 1,
            },
            "session_id": nested_uuid,
        },
    )

    await handler.on_event(event)

    saved_entity = event_repo.save.await_args.args[1]
    assert saved_entity.session_id == event.session_id
    assert saved_entity.content["session_id"] == str(nested_uuid)
    assert saved_entity.content["progress"]["session_id"] == str(nested_uuid)
