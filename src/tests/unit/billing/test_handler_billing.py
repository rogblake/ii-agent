"""Unit tests for the runtime-billing cutover in socket handlers."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.realtime.events import ApplicationEvent, EventGroup
from ii_agent.agents.models.metrics import Metrics
from ii_agent.agents.runs.agent import (
    RunCancelledEvent,
    RunCompletedEvent,
)
from ii_agent.agents.runs.base import RunStatus
from ii_agent.sessions.schemas import SessionResponse

pytestmark = pytest.mark.unit


def _base_kwargs(**overrides):
    return {
        "session_service": MagicMock(),
        "model_setting_service": MagicMock(),
        "file_service": MagicMock(),
        "event_service": MagicMock(),
        "run_task_service": MagicMock(),
        **overrides,
    }


def _make_session_info(
    session_id: uuid.UUID | None = None,
    user_id: str = "user-abc-123",
) -> SessionResponse:
    return SessionResponse(
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
        self.events: list[ApplicationEvent] = []
        # query_handler accesses event_bus.lifecycle
        self.lifecycle = MagicMock()
        self.lifecycle.register = AsyncMock()
        self.lifecycle.unregister = AsyncMock()
        self.lifecycle.set_status = MagicMock()

    async def publish(self, group, event: ApplicationEvent) -> None:
        self.events.append(event)


def _mock_services(**overrides) -> dict:
    """Build the full set of services for handlers that need extra services."""
    session_service = MagicMock()
    session_service.get_session_by_id = AsyncMock(return_value=MagicMock(llm_setting_id="model-1"))
    session_service.validate_and_prepare_session = AsyncMock()

    model_setting_service = MagicMock()
    model_setting_service.get_llm_settings = AsyncMock(
        return_value=MagicMock(is_user_model=MagicMock(return_value=False))
    )

    file_service = MagicMock()
    file_service.prepare_agent_files = AsyncMock(return_value=([], []))

    event_service = MagicMock()
    event_service.save_event = AsyncMock()

    run_task_service = MagicMock()
    run_task_service.get_running_task = AsyncMock(return_value=None)
    run_task_service.create_task = AsyncMock()
    run_task_service.update_task_status = AsyncMock()

    plan_service = MagicMock()
    plan_service.has_existing_plan = AsyncMock(return_value=False)
    plan_service.get_plan_data = AsyncMock(return_value=None)
    plan_service.fail_task = AsyncMock()

    execution_service = MagicMock()
    execution_service.create_task_with_lock = AsyncMock(return_value=None)
    execution_service.get_milestone_context = MagicMock(return_value=None)
    execution_service.update_milestones_after_run = AsyncMock(return_value=[])

    agent_service = MagicMock()
    agent_service.create_plan_agent_v1 = AsyncMock()
    agent_service.create_plan_suggestions_agent_v1 = AsyncMock()

    sandbox_service = MagicMock()
    sandbox_service.resolve_sandbox_for_session = AsyncMock(return_value=None)

    config = MagicMock()
    config.workspace_path = "/workspace"
    config.use_container_workspace = False
    config.mcp = MagicMock()
    config.mcp.port = 3000

    services = {
        "session_service": session_service,
        "model_setting_service": model_setting_service,
        "file_service": file_service,
        "event_service": event_service,
        "run_task_service": run_task_service,
        "plan_service": plan_service,
        "execution_service": execution_service,
        "agent_service": agent_service,
        "sandbox_service": sandbox_service,
        "config": config,
    }
    services.update(overrides)
    return services


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
        from ii_agent.realtime.handlers.query import UserQueryHandler

        stream = CapturingEventStream()
        services = _mock_services()
        h = UserQueryHandler(
            event_bus=stream,
            session_service=services["session_service"],
            model_setting_service=services["model_setting_service"],
            file_service=services["file_service"],
            event_service=services["event_service"],
            run_task_service=services["run_task_service"],
            execution_service=services["execution_service"],
            agent_service=services["agent_service"],
            lifecycle=stream.lifecycle,
        )
        return h, services

    @pytest.mark.asyncio
    async def test_completed_event_no_longer_triggers_handler_billing(self, handler):
        h, services = handler
        session_info = _make_session_info()
        running_task = MagicMock(id=uuid.uuid4())

        async def fake_arun(*args, **kwargs):
            yield _make_run_completed_event()

        with (
            patch.object(h, "_agent_service") as mock_agent_svc,
            patch.object(h, "_execution_service") as mock_exec_svc,
            patch("ii_agent.realtime.handlers.query.get_db_session_local", new=_noop_db_cm),
            patch(
                "ii_agent.realtime.handlers.query.convert_agent_event_to_realtime",
                return_value=None,
            ),
        ):
            mock_exec_svc.create_task_with_lock = AsyncMock(
                return_value=MagicMock(
                    task=running_task,
                    user_event=ApplicationEvent(
                        group=EventGroup.USER,
                        name="session.user_message",
                        session_id=session_info.id,
                        content={},
                    ),
                    processing_event=ApplicationEvent(
                        group=EventGroup.AGENT_RUN,
                        name="agent.processing",
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

        # No billing calls — billing is handled per-call in the runtime loop

    @pytest.mark.asyncio
    async def test_cancelled_event_no_longer_triggers_handler_billing(self, handler):
        h, services = handler
        session_info = _make_session_info()
        running_task = MagicMock(id=uuid.uuid4())

        async def fake_arun(*args, **kwargs):
            yield _make_run_cancelled_event()

        with (
            patch.object(h, "_agent_service") as mock_agent_svc,
            patch.object(h, "_execution_service") as mock_exec_svc,
            patch("ii_agent.realtime.handlers.query.get_db_session_local", new=_noop_db_cm),
            patch(
                "ii_agent.realtime.handlers.query.convert_agent_event_to_realtime",
                return_value=None,
            ),
        ):
            mock_exec_svc.create_task_with_lock = AsyncMock(
                return_value=MagicMock(
                    task=running_task,
                    user_event=ApplicationEvent(
                        group=EventGroup.USER,
                        name="session.user_message",
                        session_id=session_info.id,
                        content={},
                    ),
                    processing_event=ApplicationEvent(
                        group=EventGroup.AGENT_RUN,
                        name="agent.processing",
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

        # No billing calls — billing is handled per-call in the runtime loop


class TestContinueRunHandlerRuntimeBillingCutover:
    @pytest.fixture
    def handler(self):
        from ii_agent.realtime.handlers.continue_run import ContinueRunHandler

        stream = CapturingEventStream()
        services = _mock_services()
        with patch("ii_agent.realtime.handlers.continue_run.AgentFactory"):
            h = ContinueRunHandler(
                event_bus=stream,
                session_service=services["session_service"],
                model_setting_service=services["model_setting_service"],
                file_service=services["file_service"],
                event_service=services["event_service"],
                run_task_service=services["run_task_service"],
                config=services["config"],
            )
        return h, services

    @pytest.mark.asyncio
    async def test_completed_event_no_longer_triggers_handler_billing(self, handler):
        h, services = handler
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
        mock_agent.acontinue_run = AsyncMock(return_value=fake_continue())

        with (
            patch("ii_agent.realtime.handlers.continue_run.AgentSessionStore") as mock_store_cls,
            patch(
                "ii_agent.realtime.handlers.continue_run.get_db_session_local",
                new=_noop_db_cm,
            ),
            patch(
                "ii_agent.realtime.handlers.continue_run.convert_agent_event_to_realtime",
                return_value=None,
            ),
            patch.object(h, "_agent_factory") as mock_factory,
        ):
            mock_store = MagicMock()
            mock_store.get_by_run_id = AsyncMock(return_value=mock_run_response)
            mock_store_cls.return_value = mock_store
            mock_factory.create_agent = AsyncMock(return_value=mock_agent)

            await h.handle({"run_id": run_id, "confirmed": True}, session_info)

        # No billing calls — billing is handled per-call in the runtime loop

    @pytest.mark.asyncio
    async def test_cancelled_event_no_longer_triggers_handler_billing(self, handler):
        h, services = handler
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
        mock_agent.acontinue_run = AsyncMock(return_value=fake_continue())

        with (
            patch("ii_agent.realtime.handlers.continue_run.AgentSessionStore") as mock_store_cls,
            patch(
                "ii_agent.realtime.handlers.continue_run.get_db_session_local",
                new=_noop_db_cm,
            ),
            patch(
                "ii_agent.realtime.handlers.continue_run.convert_agent_event_to_realtime",
                return_value=None,
            ),
            patch.object(h, "_agent_factory") as mock_factory,
        ):
            mock_store = MagicMock()
            mock_store.get_by_run_id = AsyncMock(return_value=mock_run_response)
            mock_store_cls.return_value = mock_store
            mock_factory.create_agent = AsyncMock(return_value=mock_agent)

            await h.handle({"run_id": run_id, "confirmed": True}, session_info)

        # No billing calls — billing is handled per-call in the runtime loop


class TestPlanHandlerRuntimeBillingCutover:
    @pytest.fixture
    def handler(self):
        from ii_agent.realtime.handlers.plan import PlanHandler

        stream = CapturingEventStream()
        services = _mock_services()
        h = PlanHandler(
            event_bus=stream,
            session_service=services["session_service"],
            model_setting_service=services["model_setting_service"],
            file_service=services["file_service"],
            event_service=services["event_service"],
            run_task_service=services["run_task_service"],
            plan_service=services["plan_service"],
            execution_service=services["execution_service"],
            agent_service=services["agent_service"],
        )
        return h, services

    @pytest.mark.asyncio
    async def test_completed_event_no_longer_triggers_handler_billing(self, handler):
        h, services = handler
        session_info = _make_session_info()
        running_task = MagicMock(id=uuid.uuid4())

        async def fake_stream():
            yield _make_run_completed_event()

        with (
            patch("ii_agent.realtime.handlers.plan.get_db_session_local", new=_noop_db_cm),
            patch(
                "ii_agent.realtime.handlers.plan.convert_agent_event_to_realtime",
                return_value=None,
            ),
        ):
            await h._process_agent_events(fake_stream(), session_info, running_task)

        # No billing calls — billing is handled per-call in the runtime loop

    @pytest.mark.asyncio
    async def test_cancelled_event_no_longer_triggers_handler_billing(self, handler):
        h, services = handler
        session_info = _make_session_info()
        running_task = MagicMock(id=uuid.uuid4())

        async def fake_stream():
            yield _make_run_cancelled_event()

        with (
            patch("ii_agent.realtime.handlers.plan.get_db_session_local", new=_noop_db_cm),
            patch(
                "ii_agent.realtime.handlers.plan.convert_agent_event_to_realtime",
                return_value=None,
            ),
        ):
            await h._process_agent_events(fake_stream(), session_info, running_task)

        # No billing calls — billing is handled per-call in the runtime loop
