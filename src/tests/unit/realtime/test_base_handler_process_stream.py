from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agents.runs.agent import (
    RunCancelledEvent,
    RunCompletedEvent,
    RunPausedEvent,
)
from ii_agent.realtime.handlers.base import BaseCommandHandler, CommandType
from ii_agent.tasks.types import RunStatus


pytestmark = pytest.mark.unit


class _StubHandler(BaseCommandHandler):
    def get_command_type(self) -> CommandType:
        return CommandType.PING

    async def handle(self, content, session_info) -> None:
        return None


class _CapturingPubSub:
    def __init__(self) -> None:
        self.publish = AsyncMock()


def _make_handler():
    pubsub = _CapturingPubSub()
    container = MagicMock()
    container.run_task_service = MagicMock()
    container.run_task_service.transition_status = AsyncMock()
    return _StubHandler(pubsub=pubsub, container=container), pubsub, container


def _make_session_info():
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        api_version="v1",
    )


@asynccontextmanager
async def _db_cm():
    yield AsyncMock()


async def _stream(*events):
    for event in events:
        yield event


class TestProcessAgentEventStream:
    @pytest.mark.asyncio
    async def test_cancelled_run_stays_cancelled(self):
        handler, pubsub, container = _make_handler()
        session_info = _make_session_info()
        run_id = uuid.uuid4()

        event = RunCancelledEvent(
            session_id=str(session_info.id),
            agent_id="agent-1",
            agent_name="II-Agent",
            run_id=str(run_id),
            model="test-model",
            reason="User cancelled",
        )

        with patch(
            "ii_agent.realtime.handlers.base.get_db_session_local",
            return_value=_db_cm(),
        ):
            final_status = await handler.process_agent_event_stream(
                _stream(event),
                session_info,
                run_id=run_id,
            )

        assert final_status == RunStatus.CANCELLED
        container.run_task_service.transition_status.assert_awaited_once()
        assert (
            container.run_task_service.transition_status.await_args.kwargs["to_status"]
            == RunStatus.CANCELLED
        )
        published_names = [call.args[0].name for call in pubsub.publish.await_args_list]
        assert "agent.response.interrupted" in published_names

    @pytest.mark.asyncio
    async def test_paused_run_stays_paused(self):
        handler, _pubsub, container = _make_handler()
        session_info = _make_session_info()
        run_id = uuid.uuid4()

        event = RunPausedEvent(
            session_id=str(session_info.id),
            agent_id="agent-1",
            agent_name="II-Agent",
            run_id=str(run_id),
            model="test-model",
            content="Awaiting confirmation",
        )

        with patch(
            "ii_agent.realtime.handlers.base.get_db_session_local",
            return_value=_db_cm(),
        ):
            final_status = await handler.process_agent_event_stream(
                _stream(event),
                session_info,
                run_id=run_id,
            )

        assert final_status == RunStatus.PAUSED
        container.run_task_service.transition_status.assert_awaited_once()
        assert (
            container.run_task_service.transition_status.await_args.kwargs["to_status"]
            == RunStatus.PAUSED
        )

    @pytest.mark.asyncio
    async def test_completed_run_without_run_output_stays_completed(self):
        handler, _pubsub, container = _make_handler()
        session_info = _make_session_info()
        run_id = uuid.uuid4()

        event = RunCompletedEvent(
            session_id=str(session_info.id),
            agent_id="agent-1",
            agent_name="II-Agent",
            run_id=str(run_id),
            model="test-model",
            status=RunStatus.COMPLETED,
        )

        with patch(
            "ii_agent.realtime.handlers.base.get_db_session_local",
            return_value=_db_cm(),
        ):
            final_status = await handler.process_agent_event_stream(
                _stream(event),
                session_info,
                run_id=run_id,
            )

        assert final_status == RunStatus.COMPLETED
        container.run_task_service.transition_status.assert_awaited_once()
        assert (
            container.run_task_service.transition_status.await_args.kwargs["to_status"]
            == RunStatus.COMPLETED
        )
