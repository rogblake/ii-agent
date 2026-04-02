from types import SimpleNamespace

import pytest

from ii_agent.projects.exceptions import ProjectNotFoundError
from ii_agent.projects.service import ProjectService


class FakeProjectRepo:
    def __init__(self):
        self.created = []
        self.updated = []
        self.by_session = {}
        self.by_id = {}

    async def create(self, db, project):
        self.created.append(project)
        self.by_session[(project.session_id, project.user_id)] = project
        self.by_id[project.id] = project
        return project

    async def get_by_session_and_user(self, db, session_id, user_id):
        return self.by_session.get((session_id, user_id))

    async def get_by_id_and_user(self, db, project_id, user_id):
        project = self.by_id.get(project_id)
        if project and project.user_id == user_id:
            return project
        return None

    async def get_by_id(self, db, project_id):
        return self.by_id.get(project_id)

    async def update(self, db, project):
        self.updated.append(project)
        return project


class FakeSessionRepo:
    def __init__(self, session=None):
        self.session = session

    async def get_by_id(self, db, session_id):
        return self.session


@pytest.mark.asyncio
async def test_create_project_returns_none_when_session_missing(settings_factory):
    service = ProjectService(
        project_repo=FakeProjectRepo(),
        session_repo=FakeSessionRepo(session=None),
        config=settings_factory(),
    )

    result = await service.create_project(
        db=None,
        session_id="s1",
        project_name="demo",
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_session_project_raises_when_missing(settings_factory):
    service = ProjectService(
        project_repo=FakeProjectRepo(),
        session_repo=FakeSessionRepo(),
        config=settings_factory(),
    )

    with pytest.raises(ProjectNotFoundError):
        await service.get_session_project(db=None, session_id="s1", user_id="u1")


@pytest.mark.asyncio
async def test_update_session_project_production_url_persists(settings_factory):
    project_repo = FakeProjectRepo()
    session = SimpleNamespace(id="s1", user_id="u1")
    service = ProjectService(
        project_repo=project_repo,
        session_repo=FakeSessionRepo(session=session),
        config=settings_factory(),
    )

    created = await service.create_project(db=None, session_id="s1", project_name="demo")
    updated = await service.update_session_project_production_url(
        db=None,
        session_id="s1",
        user_id="u1",
        production_url="https://demo.app",
    )

    assert created is not None
    assert updated.production_url == "https://demo.app"
