from types import SimpleNamespace

import pytest

from ii_agent.sessions.exceptions import SessionNotFoundError, SessionValidationError
from ii_agent.sessions.fork_service import SessionForkService
from ii_agent.sessions.schemas import ForkContext, ForkSessionRequest, ForkType, SandboxMode


class FakeSessionRepo:
    def __init__(self, parent=None):
        self.parent = parent
        self.created = None

    async def get_by_id_and_user(self, db, session_id, user_id):
        if self.parent and session_id == self.parent.id and user_id == self.parent.user_id:
            return self.parent
        return None

    async def create(self, db, session):
        self.created = session
        return session


class FakeSandboxRepo:
    def __init__(self, sandbox=None):
        self.sandbox = sandbox

    async def get_by_session_id(self, db, session_id):
        return self.sandbox


@pytest.mark.asyncio
async def test_fork_session_validates_parent_and_source(settings_factory):
    parent = SimpleNamespace(
        id="parent-1",
        user_id="u1",
        name="Research",
        agent_type="deep_research",
        llm_setting_id="llm-1",
    )
    session_repo = FakeSessionRepo(parent=parent)
    sandbox_repo = FakeSandboxRepo(sandbox=SimpleNamespace(id="sb-1"))

    service = SessionForkService(
        session_repo=session_repo,
        sandbox_repo=sandbox_repo,
        config=settings_factory(),
    )

    request = ForkSessionRequest(
        fork_type=ForkType.RESEARCH_TO_WEBSITE,
        sandbox_mode=SandboxMode.SHARE,
        context=ForkContext(attachments=["file-1"]),
    )

    response = await service.fork_session(
        db=None,
        parent_session_id="parent-1",
        user_id="u1",
        request=request,
    )

    assert response.parent_session_id == "parent-1"
    assert response.sandbox_id == "sb-1"
    assert response.llm_setting_id == "llm-1"


@pytest.mark.asyncio
async def test_fork_session_raises_when_parent_missing(settings_factory):
    service = SessionForkService(
        session_repo=FakeSessionRepo(parent=None),
        sandbox_repo=FakeSandboxRepo(),
        config=settings_factory(),
    )

    request = ForkSessionRequest(
        fork_type=ForkType.RESEARCH_TO_WEBSITE,
        sandbox_mode=SandboxMode.NEW,
        context=ForkContext(attachments=["file-1"]),
    )

    with pytest.raises(SessionNotFoundError):
        await service.fork_session(None, "missing", "u1", request)


@pytest.mark.asyncio
async def test_fork_session_rejects_invalid_source_agent(settings_factory):
    parent = SimpleNamespace(
        id="parent-1",
        user_id="u1",
        name="General",
        agent_type="general",
        llm_setting_id=None,
    )
    service = SessionForkService(
        session_repo=FakeSessionRepo(parent=parent),
        sandbox_repo=FakeSandboxRepo(),
        config=settings_factory(),
    )

    request = ForkSessionRequest(
        fork_type=ForkType.RESEARCH_TO_WEBSITE,
        sandbox_mode=SandboxMode.NEW,
        context=ForkContext(attachments=["file-1"]),
    )

    with pytest.raises(SessionValidationError):
        await service.fork_session(None, "parent-1", "u1", request)
