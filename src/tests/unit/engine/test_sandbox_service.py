from types import SimpleNamespace
from uuid import uuid4

import pytest

from ii_agent.engine.sandboxes.schemas import SandboxStatus
from ii_agent.engine.sandboxes.service import SandboxService


class FakeSandboxRepo:
    def __init__(self, by_session=None, by_id=None):
        self.by_session = by_session
        self.by_id_record = by_id

    async def get_by_session_id(self, db, session_id):
        return self.by_session

    async def get_by_id(self, db, sandbox_id):
        return self.by_id_record


@pytest.mark.asyncio
async def test_get_sandbox_status_returns_not_initialized_when_missing(settings_factory):
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo(by_session=None),
        config=settings_factory(),
    )

    status = await service.get_sandbox_status_by_session(None, uuid4())

    assert status == SandboxStatus.NOT_INITIALIZED.value


@pytest.mark.asyncio
async def test_resolve_sandbox_for_session_falls_back_to_session_sandbox_id(settings_factory):
    sandbox_record = SimpleNamespace(id="sb-record")
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo(by_session=None, by_id=sandbox_record),
        config=settings_factory(),
    )

    async def _get_session_by_id(db, session_id):
        return SimpleNamespace(sandbox_id="11111111-1111-1111-1111-111111111111")

    session_service = SimpleNamespace(
        get_session_by_id=_get_session_by_id
    )

    resolved = await service.resolve_sandbox_for_session(None, uuid4(), session_service=session_service)

    assert resolved is sandbox_record
