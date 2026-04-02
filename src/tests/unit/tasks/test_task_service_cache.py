"""Unit tests for RunTaskService cache behavior."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.core.redis.cache import MemoryEntityCache
from ii_agent.tasks.types import RunStatus, TaskType

pytestmark = pytest.mark.unit


def _make_task_orm(**overrides):
    """Create a mock ORM RunTask object."""
    defaults = {
        "id": uuid.uuid4(),
        "session_id": uuid.uuid4(),
        "task_type": TaskType.AGENT_RUN,
        "status": RunStatus.RUNNING,
        "error_message": None,
        "data": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    defaults.update(overrides)
    obj = MagicMock()
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


class TestRunTaskServiceCache:
    def _make_service(self):
        from ii_agent.tasks.service import RunTaskService

        task_repo = AsyncMock()
        log_repo = AsyncMock()
        cache = MemoryEntityCache(namespace="tasks")
        config = MagicMock()
        svc = RunTaskService(task_repo=task_repo, log_repo=log_repo, cache=cache, config=config)
        return svc, task_repo, log_repo, cache

    @pytest.mark.asyncio
    async def test_get_task_by_id_populates_cache_on_miss(self):
        svc, task_repo, _, cache = self._make_service()
        task_id = uuid.uuid4()
        task_orm = _make_task_orm(id=task_id)
        task_repo.get_by_id = AsyncMock(return_value=task_orm)
        db = AsyncMock()

        result = await svc.get_task_by_id(db, task_id=task_id)

        assert result is not None
        assert result.id == task_id
        task_repo.get_by_id.assert_awaited_once_with(db, task_id)

        # Cache should now have the value
        cached = await cache.get(f"run_task:{task_id}")
        assert cached is not None

    @pytest.mark.asyncio
    async def test_get_task_by_id_returns_from_cache_on_hit(self):
        svc, task_repo, _, cache = self._make_service()
        task_id = uuid.uuid4()

        # Pre-populate cache
        from ii_agent.tasks.schemas import RunTaskResponse

        task_orm = _make_task_orm(id=task_id)
        response = RunTaskResponse.model_validate(task_orm)
        await cache.set(f"run_task:{task_id}", response.model_dump(mode="json"))

        db = AsyncMock()
        result = await svc.get_task_by_id(db, task_id=task_id)

        assert result is not None
        assert result.id == task_id
        # DB should NOT be called
        task_repo.get_by_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_transition_status_evicts_cache(self):
        svc, task_repo, log_repo, cache = self._make_service()
        task_id = uuid.uuid4()
        task_orm = _make_task_orm(id=task_id, status=RunStatus.RUNNING)
        task_repo.get_by_id = AsyncMock(return_value=task_orm)
        task_repo.update = AsyncMock(return_value=task_orm)
        log_repo.save = AsyncMock()

        # Pre-populate cache
        await cache.set(f"run_task:{task_id}", {"id": str(task_id)})

        db = AsyncMock()
        await svc.transition_status(db, task_id=task_id, to_status=RunStatus.COMPLETED)

        # Cache should be evicted
        cached = await cache.get(f"run_task:{task_id}")
        assert cached is None

    @pytest.mark.asyncio
    async def test_claim_task_does_not_use_cache(self):
        svc, task_repo, log_repo, cache = self._make_service()
        task_orm = _make_task_orm()
        task_repo.save = AsyncMock(return_value=task_orm)
        log_repo.save = AsyncMock()

        db = AsyncMock()
        result = await svc.claim_task(
            db,
            session_id=uuid.uuid4(),
            task_type=TaskType.AGENT_RUN,
        )

        assert result is not None
        # Cache should NOT have anything (claim doesn't cache)
        cached = await cache.get(f"run_task:{result.id}")
        assert cached is None

    @pytest.mark.asyncio
    async def test_get_task_by_id_returns_none_for_missing(self):
        svc, task_repo, _, cache = self._make_service()
        task_repo.get_by_id = AsyncMock(return_value=None)

        db = AsyncMock()
        result = await svc.get_task_by_id(db, task_id=uuid.uuid4())

        assert result is None
