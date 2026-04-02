import uuid
from types import SimpleNamespace

import pytest

from ii_agent.agents.sandboxes.types import SandboxProviderType, SandboxStatus
from ii_agent.sessions.exceptions import SessionNotFoundError, SessionValidationError
from ii_agent.sessions.fork_service import SessionForkService
from ii_agent.sessions.schemas import ForkContext, ForkSessionRequest, ForkType, SandboxMode


class FakeSessionRepo:
    def __init__(self, parent=None):
        self.parent = parent
        self.saved = None

    async def get_by_id_and_user(self, db, session_id, user_id):
        if self.parent and session_id == self.parent.id and user_id == self.parent.user_id:
            return self.parent
        return None

    async def save(self, db, session):
        self.saved = session
        return session


class FakeSandboxRepo:
    def __init__(self, sandbox=None):
        self.sandbox = sandbox
        self.saved = None

    async def get_by_session_id(self, db, session_id):
        return self.sandbox

    async def save(self, db, sandbox):
        self.saved = sandbox
        return sandbox


@pytest.mark.asyncio
async def test_fork_session_serializes_metadata_and_inherits_model_setting(settings_factory):
    parent_id = uuid.uuid4()
    user_id = uuid.uuid4()
    model_setting_id = uuid.uuid4()
    parent = SimpleNamespace(
        id=parent_id,
        user_id=user_id,
        name="Research",
        agent_type="deep_research",
        model_setting_id=model_setting_id,
    )
    session_repo = FakeSessionRepo(parent=parent)
    service = SessionForkService(
        session_repo=session_repo,
        sandbox_repo=FakeSandboxRepo(),
        config=settings_factory(),
    )

    request = ForkSessionRequest(
        fork_type=ForkType.RESEARCH_TO_WEBSITE,
        sandbox_mode=SandboxMode.SHARE,
        context=ForkContext(
            attachments=["file-1"],
            additional_instruction="Focus on structure.",
        ),
    )

    response = await service.fork_session(
        db=None,
        parent_session_id=parent_id,
        user_id=user_id,
        request=request,
    )

    assert response.parent_session_id == parent_id
    assert response.model_setting_id == model_setting_id
    assert session_repo.saved is not None
    assert session_repo.saved.parent_session_id == parent_id
    assert session_repo.saved.session_metadata == {
        "fork_info": {
            "fork_type": "research_to_website",
            "parent_session_id": str(parent_id),
            "parent_agent_type": "deep_research",
            "context": {
                "attachments": ["file-1"],
                "additional_instruction": "Focus on structure.",
            },
            "forked_at": session_repo.saved.session_metadata["fork_info"]["forked_at"],
        }
    }
    assert isinstance(session_repo.saved.session_metadata["fork_info"]["parent_session_id"], str)


@pytest.mark.asyncio
async def test_fork_session_shares_parent_sandbox_record(settings_factory):
    parent_id = uuid.uuid4()
    user_id = uuid.uuid4()
    parent = SimpleNamespace(
        id=parent_id,
        user_id=user_id,
        name="Research",
        agent_type="deep_research",
        model_setting_id=None,
    )
    shared_provider_data = {"ports": {"3000": "https://sandbox.example"}}
    sandbox_repo = FakeSandboxRepo(
        sandbox=SimpleNamespace(
            provider=SandboxProviderType.E2B,
            provider_sandbox_id="sbx-parent",
            status=SandboxStatus.RUNNING,
            expired_at=None,
            provider_data=shared_provider_data,
        )
    )
    service = SessionForkService(
        session_repo=FakeSessionRepo(parent=parent),
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
        parent_session_id=parent_id,
        user_id=user_id,
        request=request,
    )

    assert response.sandbox_mode == SandboxMode.SHARE
    assert sandbox_repo.saved is not None
    assert sandbox_repo.saved.session_id == response.session_id
    assert sandbox_repo.saved.provider == SandboxProviderType.E2B
    assert sandbox_repo.saved.provider_sandbox_id == "sbx-parent"
    assert sandbox_repo.saved.status == SandboxStatus.RUNNING
    assert sandbox_repo.saved.provider_data == shared_provider_data
    assert sandbox_repo.saved.provider_data is not shared_provider_data


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
        await service.fork_session(None, uuid.uuid4(), uuid.uuid4(), request)


@pytest.mark.asyncio
async def test_fork_session_rejects_invalid_source_agent(settings_factory):
    parent = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="General",
        agent_type="general",
        model_setting_id=None,
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
        await service.fork_session(None, parent.id, parent.user_id, request)
