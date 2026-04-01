from types import SimpleNamespace
from uuid import uuid4

import pytest

from ii_agent.agents.sandboxes.schemas import SandboxStatus
from ii_agent.agents.sandboxes.service import SandboxService


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


