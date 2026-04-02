import uuid
from types import SimpleNamespace

import pytest

from ii_agent.agents.sandboxes.service import SandboxService
from ii_agent.agents.sandboxes.types import SandboxProviderType, SandboxStatus


class FakeSandboxRepo:
    def __init__(self, records_by_session_id):
        self.records_by_session_id = records_by_session_id

    async def get_active_by_session_id(self, db, session_id):
        return self.records_by_session_id.get(session_id)


class FakeSessionRepo:
    def __init__(self, sessions_by_id):
        self.sessions_by_id = sessions_by_id

    async def get_by_id(self, db, session_id):
        return self.sessions_by_id.get(session_id)


@pytest.mark.asyncio
async def test_get_by_session_id_falls_back_to_parent_session(settings_factory):
    parent_id = uuid.uuid4()
    child_id = uuid.uuid4()
    parent_record = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=parent_id,
        provider=SandboxProviderType.E2B,
        provider_sandbox_id="sbx-parent",
        status=SandboxStatus.RUNNING,
        expired_at=None,
        provider_data={"source": "parent"},
    )
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo({parent_id: parent_record}),
        session_repo=FakeSessionRepo(
            {
                child_id: SimpleNamespace(id=child_id, parent_session_id=parent_id),
            }
        ),
        config=settings_factory(),
    )

    record = await service.get_by_session_id(None, child_id)

    assert record is parent_record


@pytest.mark.asyncio
async def test_get_sandbox_for_session_uses_parent_sandbox_for_fork(settings_factory, monkeypatch):
    parent_id = uuid.uuid4()
    child_id = uuid.uuid4()
    parent_record = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=parent_id,
        provider=SandboxProviderType.E2B,
        provider_sandbox_id="sbx-parent",
        status=SandboxStatus.RUNNING,
        expired_at=None,
        provider_data={"source": "parent"},
    )
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo({parent_id: parent_record}),
        session_repo=FakeSessionRepo(
            {
                child_id: SimpleNamespace(id=child_id, parent_session_id=parent_id),
            }
        ),
        config=settings_factory(),
    )
    expected_sandbox = SimpleNamespace(provider_sandbox_id="sbx-parent")

    async def fake_connect(record):
        assert record is parent_record
        return expected_sandbox

    monkeypatch.setattr(service, "_connect_provider", fake_connect)

    sandbox = await service.get_sandbox_for_session(None, child_id)

    assert sandbox is expected_sandbox
