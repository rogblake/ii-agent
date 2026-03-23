"""Unit tests for the runtime-billing cutover in socket handlers."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.agent.runtime.models.metrics import Metrics
from ii_agent.agent.runtime.run.agent import (
    RunCancelledEvent,
    RunCompletedEvent,
)
from ii_agent.agent.runtime.run.base import RunStatus
from ii_agent.sessions.schemas import SessionInfo

pytestmark = pytest.mark.unit


def _make_session_info(
    session_id: uuid.UUID | None = None,
    user_id: str = "user-abc-123",
) -> SessionInfo:
    return SessionInfo(
        id=session_id or uuid.uuid4(),
        user_id=user_id,
        api_version="v1",
        name="Test Session",
        status="active",
        workspace_dir="/workspace",
        is_public=False,
        created_at="2024-01-01T00:00:00Z",
        agent_type="general",
    )


class CapturingEventStream:
    def __init__(self):
        self.events: list[RealtimeEvent] = []

    async def publish(self, event: RealtimeEvent) -> None:
        self.events.append(event)


def _mock_container(**overrides) -> MagicMock:
    container = MagicMock()
    container.config = MagicMock()
    container.config.workspace_path = "/workspace"
    container.config.use_container_workspace = False
    container.config.mcp = MagicMock()
    container.config.mcp.port = 3000
    container.session_service = MagicMock()
    container.session_service.get_session_by_id = AsyncMock(
        return_value=MagicMock(llm_setting_id="model-1")
    )
    container.sandbox_service = MagicMock()
    container.sandbox_service.resolve_sandbox_for_session = AsyncMock(return_value=None)
    container.project_service = MagicMock()
    container.project_service.get_session_project_or_none = AsyncMock(return_value=None)
    container.agent_run_service = MagicMock()
    container.agent_run_service.get_running_task = AsyncMock(return_value=None)
    container.agent_run_service.create_task = AsyncMock()
    container.agent_run_service.update_task_status = AsyncMock()
    container.event_service = MagicMock()
    container.event_service.save_event = AsyncMock()
    container.file_service = MagicMock()
    container.file_service.prepare_agent_files = AsyncMock(return_value=([], []))
    container.session_validation_service = MagicMock()
    container.llm_setting_service = MagicMock()
    container.llm_setting_service.get_llm_settings = AsyncMock(
        return_value=MagicMock(is_user_model=MagicMock(return_value=False))
    )
    container.plan_service = MagicMock()
    container.plan_service.has_existing_plan = AsyncMock(return_value=False)
    container.plan_service.get_plan_data = AsyncMock(return_value=None)
    container.plan_service.fail_task = AsyncMock()
    container.execution_service = MagicMock()
    container.execution_service.create_task_with_lock = AsyncMock(return_value=None)
    container.execution_service.get_milestone_context = MagicMock(return_value=None)
    container.execution_service.update_milestones_after_run = AsyncMock(return_value=[])
    container.agent_service = MagicMock()
    container.agent_service.create_plan_agent_v1 = AsyncMock()
    container.agent_service.create_plan_suggestions_agent_v1 = AsyncMock()
    container.llm_billing_service = MagicMock()
    for key, value in overrides.items():
        setattr(container, key, value)
    return container


@asynccontextmanager
async def _noop_db_cm():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.begin_nested = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(),
            __aexit__=AsyncMock(),
        )
    )
    yield db


def _make_metrics(
    input_tokens: int = 100,
    output_tokens: int = 50,
    duration: float = 1.5,
    cost: float = 0.002,
) -> Metrics:
    return Metrics(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration=duration,
        cost=cost,
    )


def _make_run_completed_event(run_id: str | None = None) -> RunCompletedEvent:
    return RunCompletedEvent(
        session_id="session-abc",
        agent_id="agent-001",
        agent_name="TestAgent",
        run_id=run_id or str(uuid.uuid4()),
        model="gpt-4o",
        model_provider="OpenAI",
        metrics=_make_metrics(),
        status=RunStatus.COMPLETED,
    )


def _make_run_cancelled_event(run_id: str | None = None) -> RunCancelledEvent:
    return RunCancelledEvent(
        session_id="session-abc",
        agent_id="agent-001",
        agent_name="TestAgent",
        run_id=run_id or str(uuid.uuid4()),
        model="gpt-4o",
        model_provider="OpenAI",
        reason="User cancelled",
    )


class TestQueryHandlerRuntimeBillingCutover:
    @pytest.fixture
    def handler(self):
        from ii_agent.agent.socket.command.query_handler import UserQueryHandler

        stream = CapturingEventStream()
        container = _mock_container()
        return UserQueryHandler(event_stream=stream, container=container), container

    @pytest.mark.asyncio
    async def test_completed_event_no_longer_triggers_handler_billing(self, handler):
        h, container = handler
        session_info = _make_session_info()
        running_task = MagicMock(id=uuid.uuid4())

        async def fake_arun(*args, **kwargs):
            yield _make_run_completed_event()

        with (
            patch.object(h.container, "agent_service") as mock_agent_svc,
            patch.object(h.container, "execution_service") as mock_exec_svc,
            patch(
                "ii_agent.agent.socket.command.query_handler.get_db_session_local", new=_noop_db_cm
            ),
            patch(
                "ii_agent.agent.socket.command.query_handler.convert_agent_event_to_realtime",
                return_value=None,
            ),
        ):
            mock_exec_svc.create_task_with_lock = AsyncMock(
                return_value=MagicMock(
                    task=running_task,
                    user_event=RealtimeEvent(
                        type=EventType.USER_MESSAGE,
                        session_id=session_info.id,
                        content={},
                    ),
                    processing_event=RealtimeEvent(
                        type=EventType.PROCESSING,
                        session_id=session_info.id,
                        content={},
                    ),
                )
            )
            mock_exec_svc.update_milestones_after_run = AsyncMock(return_value=[])
            mock_agent = AsyncMock()
            mock_agent.arun = AsyncMock(return_value=fake_arun())
            mock_agent_svc.create_agent_v1 = AsyncMock(return_value=mock_agent)

            await h._handle_query(
                MagicMock(
                    text="hello",
                    files=None,
                    model_id="gpt-4o",
                    tool_args={},
                    source=None,
                    thinking_tokens=0,
                    metadata=None,
                    milestone_ids=None,
                    plan_context=None,
                    github_repository=None,
                ),
                session_info,
            )

        container.llm_billing_service.reserve_chat_llm_call.assert_not_called()
        container.llm_billing_service.settle_llm_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancelled_event_no_longer_triggers_handler_billing(self, handler):
        h, container = handler
        session_info = _make_session_info()
        running_task = MagicMock(id=uuid.uuid4())

        async def fake_arun(*args, **kwargs):
            yield _make_run_cancelled_event()

        with (
            patch.object(h.container, "agent_service") as mock_agent_svc,
            patch.object(h.container, "execution_service") as mock_exec_svc,
            patch(
                "ii_agent.agent.socket.command.query_handler.get_db_session_local", new=_noop_db_cm
            ),
            patch(
                "ii_agent.agent.socket.command.query_handler.convert_agent_event_to_realtime",
                return_value=None,
            ),
        ):
            mock_exec_svc.create_task_with_lock = AsyncMock(
                return_value=MagicMock(
                    task=running_task,
                    user_event=RealtimeEvent(
                        type=EventType.USER_MESSAGE,
                        session_id=session_info.id,
                        content={},
                    ),
                    processing_event=RealtimeEvent(
                        type=EventType.PROCESSING,
                        session_id=session_info.id,
                        content={},
                    ),
                )
            )
            mock_exec_svc.update_milestones_after_run = AsyncMock(return_value=[])
            mock_agent = AsyncMock()
            mock_agent.arun = AsyncMock(return_value=fake_arun())
            mock_agent_svc.create_agent_v1 = AsyncMock(return_value=mock_agent)

            await h._handle_query(
                MagicMock(
                    text="hello",
                    files=None,
                    model_id="gpt-4o",
                    tool_args={},
                    source=None,
                    thinking_tokens=0,
                    metadata=None,
                    milestone_ids=None,
                    plan_context=None,
                    github_repository=None,
                ),
                session_info,
            )

        container.llm_billing_service.reserve_chat_llm_call.assert_not_called()
        container.llm_billing_service.settle_llm_call.assert_not_called()


class TestContinueRunHandlerRuntimeBillingCutover:
    @pytest.fixture
    def handler(self):
        from ii_agent.agent.socket.command.continue_run_handler import ContinueRunHandler

        stream = CapturingEventStream()
        container = _mock_container()
        with patch("ii_agent.agent.socket.command.continue_run_handler.AgentFactory"):
            handler = ContinueRunHandler(event_stream=stream, container=container)
        return handler, container

    @pytest.mark.asyncio
    async def test_completed_event_no_longer_triggers_handler_billing(self, handler):
        h, container = handler
        session_info = _make_session_info()
        run_id = str(uuid.uuid4())

        mock_run_response = MagicMock(
            run_id=run_id,
            tools=[],
            tools_requiring_confirmation=[],
            tools_requiring_user_input=[],
        )

        async def fake_continue(*args, **kwargs):
            yield _make_run_completed_event(run_id=run_id)

        mock_agent = MagicMock()
        mock_agent.acontinue_run = MagicMock(return_value=fake_continue())

        with (
            patch(
                "ii_agent.agent.socket.command.continue_run_handler.AgentSessionStore"
            ) as mock_store_cls,
            patch(
                "ii_agent.agent.socket.command.continue_run_handler.get_db_session_local",
                new=_noop_db_cm,
            ),
            patch(
                "ii_agent.agent.socket.command.continue_run_handler.convert_agent_event_to_realtime",
                return_value=None,
            ),
            patch.object(h, "_agent_factory") as mock_factory,
        ):
            mock_store = MagicMock()
            mock_store.get_by_run_id = AsyncMock(return_value=mock_run_response)
            mock_store_cls.return_value = mock_store
            mock_factory.create_agent = AsyncMock(return_value=mock_agent)

            await h.handle({"run_id": run_id, "confirmed": True}, session_info)

        container.llm_billing_service.reserve_chat_llm_call.assert_not_called()
        container.llm_billing_service.settle_llm_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancelled_event_no_longer_triggers_handler_billing(self, handler):
        h, container = handler
        session_info = _make_session_info()
        run_id = str(uuid.uuid4())

        mock_run_response = MagicMock(
            run_id=run_id,
            tools=[],
            tools_requiring_confirmation=[],
            tools_requiring_user_input=[],
        )

        async def fake_continue(*args, **kwargs):
            yield _make_run_cancelled_event(run_id=run_id)

        mock_agent = MagicMock()
        mock_agent.acontinue_run = MagicMock(return_value=fake_continue())

        with (
            patch(
                "ii_agent.agent.socket.command.continue_run_handler.AgentSessionStore"
            ) as mock_store_cls,
            patch(
                "ii_agent.agent.socket.command.continue_run_handler.get_db_session_local",
                new=_noop_db_cm,
            ),
            patch(
                "ii_agent.agent.socket.command.continue_run_handler.convert_agent_event_to_realtime",
                return_value=None,
            ),
            patch.object(h, "_agent_factory") as mock_factory,
        ):
            mock_store = MagicMock()
            mock_store.get_by_run_id = AsyncMock(return_value=mock_run_response)
            mock_store_cls.return_value = mock_store
            mock_factory.create_agent = AsyncMock(return_value=mock_agent)

            await h.handle({"run_id": run_id, "confirmed": True}, session_info)

        container.llm_billing_service.reserve_chat_llm_call.assert_not_called()
        container.llm_billing_service.settle_llm_call.assert_not_called()


class TestPlanHandlerRuntimeBillingCutover:
    @pytest.fixture
    def handler(self):
        from ii_agent.agent.socket.command.plan_handler import PlanHandler

        stream = CapturingEventStream()
        container = _mock_container()
        return PlanHandler(event_stream=stream, container=container), container

    @pytest.mark.asyncio
    async def test_completed_event_no_longer_triggers_handler_billing(self, handler):
        h, container = handler
        session_info = _make_session_info()
        running_task = MagicMock(id=uuid.uuid4())

        async def fake_stream():
            yield _make_run_completed_event()

        with (
            patch(
                "ii_agent.agent.socket.command.plan_handler.get_db_session_local", new=_noop_db_cm
            ),
            patch(
                "ii_agent.agent.socket.command.plan_handler.convert_agent_event_to_realtime",
                return_value=None,
            ),
        ):
            await h._process_agent_events(fake_stream(), session_info, running_task)

        container.llm_billing_service.reserve_chat_llm_call.assert_not_called()
        container.llm_billing_service.settle_llm_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancelled_event_no_longer_triggers_handler_billing(self, handler):
        h, container = handler
        session_info = _make_session_info()
        running_task = MagicMock(id=uuid.uuid4())

        async def fake_stream():
            yield _make_run_cancelled_event()

        with (
            patch(
                "ii_agent.agent.socket.command.plan_handler.get_db_session_local", new=_noop_db_cm
            ),
            patch(
                "ii_agent.agent.socket.command.plan_handler.convert_agent_event_to_realtime",
                return_value=None,
            ),
        ):
            await h._process_agent_events(fake_stream(), session_info, running_task)

        container.llm_billing_service.reserve_chat_llm_call.assert_not_called()
        container.llm_billing_service.settle_llm_call.assert_not_called()
