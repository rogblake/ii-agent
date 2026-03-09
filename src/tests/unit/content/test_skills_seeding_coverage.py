"""Coverage tests for slide/storybook skill seeding helper."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ii_agent.content.skills import seeding as skills_seeding


class _FakeDbSession:
    async def __aenter__(self):
        return "db"

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_ensure_builtin_skills_synced_runs_once_for_successful_sync(monkeypatch):
    skills_seeding._skills_synced = False
    sync_mock = AsyncMock(return_value=1)

    monkeypatch.setattr(
        "ii_agent.engine.v1.skills.loader.sync_builtin_to_db",
        sync_mock,
    )
    monkeypatch.setattr("ii_agent.core.db.manager.get_db", lambda: _FakeDbSession())

    await skills_seeding.ensure_builtin_skills_synced()
    await skills_seeding.ensure_builtin_skills_synced()

    assert skills_seeding._skills_synced is True
    sync_mock.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_builtin_skills_sync_error_does_not_raise(monkeypatch):
    skills_seeding._skills_synced = False
    monkeypatch.setattr(
        "ii_agent.engine.v1.skills.loader.sync_builtin_to_db",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    monkeypatch.setattr("ii_agent.core.db.manager.get_db", lambda: _FakeDbSession())

    await skills_seeding.ensure_builtin_skills_synced()

    assert skills_seeding._skills_synced is False
