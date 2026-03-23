from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agent.runs.models import RunStatus
from ii_agent.sessions.schemas import SessionInfo


def _make_session_info() -> SessionInfo:
    return SessionInfo(
        id=uuid.uuid4(),
        user_id="user-1",
        api_version="v1",
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
    from ii_agent.agent.socket.command.cancel_handler import CancelHandler

    stream = _CapturingEventStream()
    session_info = _make_session_info()
    run_id = uuid.uuid4()

    last_task = SimpleNamespace(id=run_id, status=RunStatus.PAUSED.value)
    container = MagicMock()
    container.agent_run_service = SimpleNamespace(
        get_last_by_session_id=AsyncMock(return_value=last_task)
    )
    # Billing is handled by runtime reservations, not the cancel handler.
    container.llm_billing_service = MagicMock()

    with (
        patch(
            "ii_agent.agent.socket.command.cancel_handler.get_db_session_local",
            side_effect=lambda: _fake_db_context(),
        ),
        patch(
            "ii_agent.agent.socket.command.cancel_handler.cancel.cancel_run",
            AsyncMock(return_value=True),
        ),
    ):
        handler = CancelHandler(event_stream=stream, container=container)
        await handler.handle({}, session_info)

    # Per-call billing settled in runtime — handler must not bill directly
    container.llm_billing_service.reserve_chat_llm_call.assert_not_called()
    container.llm_billing_service.settle_llm_call.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_handler_does_not_bill_when_cancel_signal_fails():
    from ii_agent.agent.socket.command.cancel_handler import CancelHandler

    stream = _CapturingEventStream()
    session_info = _make_session_info()
    run_id = uuid.uuid4()

    last_task = SimpleNamespace(id=run_id, status=RunStatus.PAUSED.value)
    container = MagicMock()
    container.agent_run_service = SimpleNamespace(
        get_last_by_session_id=AsyncMock(return_value=last_task)
    )
    container.llm_billing_service = MagicMock()

    with (
        patch(
            "ii_agent.agent.socket.command.cancel_handler.get_db_session_local",
            side_effect=lambda: _fake_db_context(),
        ),
        patch(
            "ii_agent.agent.socket.command.cancel_handler.cancel.cancel_run",
            AsyncMock(return_value=False),
        ),
    ):
        handler = CancelHandler(event_stream=stream, container=container)
        await handler.handle({}, session_info)

    container.llm_billing_service.reserve_chat_llm_call.assert_not_called()
    container.llm_billing_service.settle_llm_call.assert_not_called()
