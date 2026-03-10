from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ii_agent.agent.application.plan_service import PlanService
from ii_agent.core.events.models import EventType


@pytest.mark.asyncio
async def test_has_existing_plan_detects_populated_milestones(settings_factory, monkeypatch):
    service = PlanService(config=settings_factory())

    async def _get_session_by_id(db, session_id):
        return SimpleNamespace(session_metadata={"plan": {"milestones": [{"id": "m1"}]}})

    session_service = SimpleNamespace(
        get_session_by_id=_get_session_by_id
    )

    @asynccontextmanager
    async def _db_cm():
        yield None

    monkeypatch.setattr("ii_agent.agent.application.plan_service.get_db_session_local", _db_cm)

    assert await service.has_existing_plan(uuid4(), session_service=session_service) is True


@pytest.mark.asyncio
async def test_save_and_emit_plan_persists_plan_event(settings_factory, monkeypatch):
    service = PlanService(config=settings_factory())

    session = SimpleNamespace(session_metadata={})

    class FakeDB:
        def __init__(self):
            self.added = []
            self.commits = 0

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.commits += 1

    db_obj = FakeDB()

    @asynccontextmanager
    async def _db_cm():
        yield db_obj

    monkeypatch.setattr("ii_agent.agent.application.plan_service.get_db_session_local", _db_cm)

    async def _get_session_by_id(db, session_id):
        return session

    session_service = SimpleNamespace(get_session_by_id=_get_session_by_id)
    saved_events = []

    async def _save_event(db, session_id, event):
        saved_events.append(event)

    event_service = SimpleNamespace(save_event=_save_event)

    events = await service.save_and_emit_plan(
        session_info=SimpleNamespace(id=uuid4()),
        plan_data={"summary": "sum", "milestones": [{"id": "m1"}]},
        session_service=session_service,
        event_service=event_service,
    )

    assert db_obj.commits == 1
    assert len(events) == 1
    assert events[0].type == EventType.PLAN_GENERATED
