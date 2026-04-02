from types import SimpleNamespace

import pytest

from ii_agent.workers.celery.model_imports import import_model_modules

import_model_modules()  # resolve all cross-model ORM relationships

from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.sessions.service import SessionService


class FakeSessionRepo:
    def __init__(self, session):
        self.session = session
        self.updated = 0

    async def get_by_id_and_user(self, db, session_id, user_id):
        return (
            self.session
            if str(self.session.id) == str(session_id) and self.session.user_id == user_id
            else None
        )

    async def update(self, db, session):
        self.updated += 1
        return session


class FakeEventRepo:
    def __init__(self):
        self.created = []
        self.latest = None

    async def get_latest_by_type(self, db, session_id, event_type):
        return self.latest

    async def create(self, db, event):
        self.created.append(event)


class FakeDB:
    def __init__(self):
        self.flush_calls = 0

    async def flush(self):
        self.flush_calls += 1


@pytest.mark.asyncio
async def test_update_session_plan_normalizes_fields_and_creates_event(settings_factory):
    session = SimpleNamespace(id="s1", user_id="u1", session_metadata={})
    session_repo = FakeSessionRepo(session)
    event_repo = FakeEventRepo()
    service = SessionService(
        session_repo=session_repo,
        event_repo=event_repo,
        run_task_service=SimpleNamespace(),
        file_store=SimpleNamespace(get_download_signed_url=lambda path: f"signed:{path}"),
        sandbox_repo=SimpleNamespace(),
        config=settings_factory(),
    )

    db = FakeDB()
    await service.update_session_plan(
        db,
        session_id="s1",
        user_id="u1",
        summary="Summary",
        milestones=[{"id": "m1", "content": "Do thing", "details": None, "dependencies": None}],
    )

    milestone = session.session_metadata["plan"]["milestones"][0]
    assert milestone["details"] == ""
    assert milestone["dependencies"] == []
    assert event_repo.created[0].type == "plan.milestone.generated"


@pytest.mark.asyncio
async def test_update_session_plan_updates_existing_plan_event(settings_factory):
    session = SimpleNamespace(id="s1", user_id="u1", session_metadata={})
    session_repo = FakeSessionRepo(session)
    existing_event = SimpleNamespace(content={})
    event_repo = FakeEventRepo()
    event_repo.latest = existing_event

    service = SessionService(
        session_repo=session_repo,
        event_repo=event_repo,
        run_task_service=SimpleNamespace(),
        file_store=SimpleNamespace(get_download_signed_url=lambda path: f"signed:{path}"),
        sandbox_repo=SimpleNamespace(),
        config=settings_factory(),
    )

    db = FakeDB()
    await service.update_session_plan(
        db,
        session_id="s1",
        user_id="u1",
        summary="Updated",
        milestones=[{"id": "m1", "content": "Done"}],
    )

    assert db.flush_calls == 1
    assert existing_event.content["summary"] == "Updated"
    assert event_repo.created == []


@pytest.mark.asyncio
async def test_update_session_plan_raises_when_session_missing(settings_factory):
    missing_repo = FakeSessionRepo(SimpleNamespace(id="other", user_id="u2", session_metadata={}))
    service = SessionService(
        session_repo=missing_repo,
        event_repo=FakeEventRepo(),
        run_task_service=SimpleNamespace(),
        file_store=SimpleNamespace(get_download_signed_url=lambda path: f"signed:{path}"),
        sandbox_repo=SimpleNamespace(),
        config=settings_factory(),
    )

    with pytest.raises(SessionNotFoundError):
        await service.update_session_plan(
            FakeDB(),
            session_id="s1",
            user_id="u1",
            summary="x",
            milestones=[],
        )
