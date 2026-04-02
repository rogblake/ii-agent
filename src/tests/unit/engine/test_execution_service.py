from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ii_agent.engine.agents.execution_service import ExecutionService
from ii_agent.engine.agents.models import RunStatus


class FakeEventService:
    def __init__(self):
        self.saved = []

    async def save_event(self, db, session_id, event):
        self.saved.append((session_id, event))


@pytest.mark.asyncio
async def test_get_milestone_context_single_and_multi(settings_factory):
    service = ExecutionService(config=settings_factory())
    plan_context = {
        "summary": "Build feature",
        "milestones": [
            {"id": "m1", "content": "Setup", "details": "init", "status": "pending"},
            {"id": "m2", "content": "Ship", "details": "deploy", "status": "pending"},
        ],
    }

    single = service.get_milestone_context(["m1"], plan_context)
    multi = service.get_milestone_context(["m1", "m2"], plan_context)
    missing = service.get_milestone_context(["missing"], plan_context)

    assert "Milestone" in single
    assert "Target Milestones to Build" in multi
    assert missing is None


@pytest.mark.asyncio
async def test_update_milestones_after_run_completed_updates_only_requested(settings_factory, monkeypatch):
    session_obj = SimpleNamespace(
        session_metadata={
            "plan": {
                "milestones": [
                    {"id": "m1", "status": "pending"},
                    {"id": "m2", "status": "pending"},
                ]
            }
        }
    )

    class FakeDB:
        def add(self, obj):
            return None

        async def commit(self):
            return None

    @asynccontextmanager
    async def _db_cm():
        yield FakeDB()

    monkeypatch.setattr("ii_agent.engine.agents.execution_service.get_db_session_local", _db_cm)

    service = ExecutionService(config=settings_factory())
    event_service = FakeEventService()

    async def _get_session_by_id(db, session_id):
        return session_obj

    session_service = SimpleNamespace(get_session_by_id=_get_session_by_id)

    events = await service.update_milestones_after_run(
        session_id=uuid4(),
        milestone_ids=["m2"],
        status=RunStatus.COMPLETED,
        session_service=session_service,
        event_service=event_service,
    )

    assert len(events) == 1
    assert session_obj.session_metadata["plan"]["milestones"][1]["status"] == "completed"
    assert session_obj.session_metadata["plan"]["milestones"][0]["status"] == "pending"
