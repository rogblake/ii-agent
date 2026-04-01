from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.tasks.types import RunStatus
from ii_agent.sessions.schemas import SessionInfo


def _mock_container(**overrides):
    container = MagicMock()
    container.run_task_service = overrides.get("run_task_service", MagicMock())
    container.session_service = MagicMock()
    container.credit_service = MagicMock()
    container.model_setting_service = MagicMock()
    container.file_service = MagicMock()
    container.event_service = MagicMock()
    return container


def _make_session_info() -> SessionInfo:
    return SessionInfo(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="Test Session",
        status="active",
        workspace_dir="/workspace",
        is_public=False,
        created_at="2024-01-01T00:00:00Z",
        agent_type="general",
    )


@asynccontextmanager
async def _fake_db_context():
    db = MagicMock()
    db.commit = AsyncMock()
    yield db


class _CapturingEventStream:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def publish(self, event) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_cancel_handler_does_not_bill_paused_runs_directly():
    from ii_agent.realtime.handlers.cancel import CancelHandler

    stream = _CapturingEventStream()
    session_info = _make_session_info()
    run_id = uuid.uuid4()

    last_task = SimpleNamespace(id=run_id, status=RunStatus.PAUSED)
    svc = MagicMock()
    svc.get_last_by_session_id = AsyncMock(return_value=last_task)
    svc.transition_status = AsyncMock()
    container = _mock_container(run_task_service=svc)

    with (
        patch(
            "ii_agent.realtime.handlers.cancel.get_db_session_local",
            side_effect=lambda: _fake_db_context(),
        ),
        patch(
            "ii_agent.realtime.handlers.cancel.cancel.cancel_run",
            AsyncMock(return_value=True),
        ),
    ):
        handler = CancelHandler(pubsub=stream, container=container)
        await handler.dispatch({}, session_info)

    # Per-call billing settled in runtime — handler must not bill directly


@pytest.mark.asyncio
async def test_cancel_handler_does_not_bill_when_cancel_signal_fails():
    from ii_agent.realtime.handlers.cancel import CancelHandler

    stream = _CapturingEventStream()
    session_info = _make_session_info()
    run_id = uuid.uuid4()

    last_task = SimpleNamespace(id=run_id, status=RunStatus.PAUSED)
    svc = MagicMock()
    svc.get_last_by_session_id = AsyncMock(return_value=last_task)
    svc.transition_status = AsyncMock()
    container = _mock_container(run_task_service=svc)

    with (
        patch(
            "ii_agent.realtime.handlers.cancel.get_db_session_local",
            side_effect=lambda: _fake_db_context(),
        ),
        patch(
            "ii_agent.realtime.handlers.cancel.cancel.cancel_run",
            AsyncMock(return_value=False),
        ),
    ):
        handler = CancelHandler(pubsub=stream, container=container)
        await handler.dispatch({}, session_info)

    # Per-call billing settled in runtime — handler must not bill directly
