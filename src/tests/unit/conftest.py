from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def fake_db_session() -> SimpleNamespace:
    return SimpleNamespace(
        add=AsyncMock(),
        execute=AsyncMock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )


@pytest.fixture
def fake_current_user() -> SimpleNamespace:
    return SimpleNamespace(id="user-1", is_active=True)


@pytest.fixture
def fake_event_stream():
    class _FakeEventStream:
        def __init__(self) -> None:
            self.published = []

        async def publish(self, *args) -> None:
            # Accepts publish(event) or publish(group, event)
            self.published.append(args[-1])

    return _FakeEventStream()


@pytest.fixture
def task_context_factory():
    def _factory(
        task_id: str = "task-1",
        *,
        session_id: str = "session-1",
        user_id: str = "user-1",
        run_id: str = "run-1",
    ):
        return SimpleNamespace(
            request=SimpleNamespace(
                id=task_id,
                headers={
                    "session_id": session_id,
                    "user_id": user_id,
                    "run_id": run_id,
                },
            )
        )

    return _factory


@pytest.fixture
def async_cm_factory():
    def _factory(value):
        @asynccontextmanager
        async def _cm():
            yield value

        return _cm

    return _factory
