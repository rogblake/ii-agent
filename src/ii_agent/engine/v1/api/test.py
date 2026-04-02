from __future__ import annotations

import json
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ii_agent.engine.agents.agent_run_service import AgentRunService
from ii_agent.engine.agents.repository import AgentRunTaskRepository
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.realtime.events.repository import EventRepository
from ii_agent.settings.llm.repository import LLMSettingRepository
from ii_agent.settings.llm.service import LLMSettingService
from ii_agent.engine.sandboxes.repository import SandboxRepository
from ii_agent.sessions.repository import SessionRepository
from ii_agent.sessions.service import SessionService
from ii_agent.core.storage.client import storage
from ii_agent.core.config.settings import get_settings
from ii_agent.core.dependencies import SettingsDep
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.engine.v1.agents.agent import IIAgent
from ii_agent.engine.v1.factory.factory import AgentFactory, PROVIDER_SPEC_MAP
from ii_agent.engine.types import AgentType
from ii_agent.engine.v1.models.utils import get_model
from ii_agent.engine.v1.run.agent import RunOutput
from ii_agent.engine.v1.agent_sessions.store import AgentSessionStore
from ii_agent.engine.v1.agent_sessions.summary import SessionSummaryManager
from ii_agent.engine.v1.tools.decorator import tool as tool_decorator

router = APIRouter(prefix="/test/agent", tags=["test-agent"])

DEFAULT_MODEL_SETTING_ID = "default"


def get_current_time() -> str:
    """Get the current date and time."""
    from datetime import datetime

    now = datetime.now()
    return f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}"


def calculate(expression: str) -> str:
    """Evaluate a mathematical expression safely. Supports +, -, *, /, %, and parentheses."""
    try:
        allowed_chars = set("0123456789+-*/().% ")
        if not all(c in allowed_chars for c in expression):
            return "Error: Only basic math operations are allowed (+, -, *, /, %, ())"
        result = eval(expression)
        return f"Result: {result}"
    except Exception as e:
        return f"Error calculating: {str(e)}"


@tool_decorator(requires_user_input=True, user_input_fields=["to_address"])
def send_email(subject: str, body: str, to_address: str) -> str:
    """
    Send an email.

    Args:
        subject (str): The subject of the email.
        body (str): The body of the email.
        to_address (str): The address to send the email to.
    """
    return f"Sent email to {to_address} with subject '{subject}' and body '{body}'"


class TestAgentPayload(BaseModel):
    """Payload for test agent endpoint."""

    stream: bool = Field(default=False, description="streaming response or not")
    message: str = Field(..., min_length=1, description="User message to send to agent")
    model_id: Optional[str] = Field(
        default=None, description="Model ID to use (defaults to system default)"
    )
    session_id: Optional[UUID] = Field(
        default=None, description="Session ID (creates new if not provided)"
    )
    tool_args: Optional[Dict[str, bool]] = Field(default_factory=dict, description="tool enabled")
    source: Optional[str] = Field(default="user")


class TestAgentResponse(BaseModel):
    """Response from test agent endpoint."""

    session_id: str
    run_id: str
    run_output: Optional[Dict[str, Any]] = None


class UserInputField(BaseModel):
    """User input field for HITL."""

    name: str
    value: Any
    field_type: Optional[str] = None
    description: Optional[str] = None


class ContinueRunPayload(BaseModel):
    """Payload for continuing a paused run with user input."""

    source: str = "system"
    model_id: str
    run_id: str = Field(..., description="Run ID of the paused run to continue")
    session_id: str = Field(..., description="Session ID")
    user_input: Optional[Dict[str, Any]] = Field(
        default=None, description="User input values for the paused tool (field_name: value)"
    )
    is_confirmed: Optional[bool] = Field(..., description="user confirmation")


class SessionSummaryPayload(BaseModel):
    """Payload for session summary endpoint."""

    session_id: UUID = Field(..., description="Session ID to generate summary for")
    model_id: Optional[str] = Field(
        default=None,
        description="Model ID to use for summary generation (defaults to system default)",
    )
    source: Optional[str] = Field(default="user")


class SessionSummaryResponse(BaseModel):
    """Response from session summary endpoint."""

    session_id: str
    summary: Optional[str] = None
    topics: Optional[List[str]] = None
    error: Optional[str] = None


async def _stream_events_as_sse(
    agent: IIAgent,
    payload: TestAgentPayload,
    session_id: str,
    run_id: Optional[str] = None,
) -> AsyncIterator[str]:
    """Generic SSE event streamer that formats agent events as Server-Sent Events.

    Args:
        event_stream: Async iterator of RunOutputEvent or RunOutput objects
        session_id: Session ID for the run
        run_id: Optional run ID (will be extracted from events if not provided)

    Yields:
        SSE formatted strings with event data
    """
    try:
        event_stream = await agent.arun(
            input=payload.message, run_id=str(uuid4()), stream=True, stream_events=True
        )
        async for event in event_stream:
            if isinstance(event, RunOutput):
                # Final RunOutput - yield as completion event
                run_id = event.run_id
                yield f"event: completed\ndata: {json.dumps(event.to_dict())}\n\n"
            else:
                # RunOutputEvent - yield the event
                event_data = event.to_dict() if hasattr(event, "to_dict") else {}
                event_type = event_data.get("event", "unknown")

                if run_id is None and event_data.get("run_id"):
                    run_id = event_data.get("run_id")

                yield f"event: {event_type}\ndata: {json.dumps(event_data)}\n\n"

    except Exception as e:
        error_data = {
            "event": "error",
            "error": str(e),
            "session_id": session_id,
            "run_id": run_id,
        }
        yield f"event: error\ndata: {json.dumps(error_data)}\n\n"

    # Send done event
    done_data = {"session_id": session_id, "run_id": run_id}
    yield f"event: done\ndata: {json.dumps(done_data)}\n\n"


_agent_factory = AgentFactory(config=get_settings())


@router.post("/general", response_model=None)
async def test_agent_stream_endpoint(
    payload: TestAgentPayload,
    current_user: CurrentUser,
    db: DBSession,
    settings: SettingsDep,
) -> StreamingResponse | TestAgentResponse:
    """Streaming test endpoint for v2 agent with new prompt system and web tools.

    This endpoint creates an IIAgent with the same configuration as the non-streaming
    endpoint but returns a Server-Sent Events (SSE) stream of events.

    Events emitted:
    - RunStarted: When the run begins
    - RunContent: Content chunks as they are generated
    - ToolCallStarted: When a tool call begins
    - ToolCallCompleted: When a tool call finishes
    - RunCompleted: Final response with full content
    - error: If an error occurs
    - done: Final event indicating stream end

    Args:
        agent_type: Type of agent - 'general', 'research', 'minimal', 'codex', or 'claude'
        payload: Request payload with message, optional model_id and session_id

    Returns:
        StreamingResponse with SSE formatted events
    """

    # Create or get session
    session_service = SessionService(
        config=settings,
        session_repo=SessionRepository(),
        event_repo=EventRepository(),
        agent_run_service=AgentRunService(repo=AgentRunTaskRepository(), config=settings),
        file_store=storage,
        sandbox_repo=SandboxRepository(),
    )
    session_info = await session_service.get_or_create_session(
        db,
        session_uuid=str(payload.session_id) if payload.session_id else None,
        user_id=current_user.id,
    )

    llm_config: LLMConfig = await LLMSettingService(
        config=settings, repo=LLMSettingRepository(), session_repo=SessionRepository()
    ).get_llm_settings(
        db,
        session=session_info,
        source=payload.source,
        model_id=payload.model_id,
    )

    workspace_path = Path(settings.workspace_path).resolve()
    workspace_manager = WorkspaceManager(
        root=workspace_path,
        container_workspace=settings.use_container_workspace,
    )

    # Create skill creator for loading user-specific skills
    from ii_agent.engine.v1.skills.db_creator import DbSkillCreator
    from ii_agent.engine.v1.tools.connectors import ConnectorTool
    from ii_agent.core.storage.client import storage

    skill_creator = DbSkillCreator(user_id=current_user.id, storage=storage)
    connector_tool = ConnectorTool(user_id=current_user.id)

    agent = await _agent_factory.create_agent(
        session_id=str(session_info.id),
        user_id=current_user.id,
        session_store=AgentSessionStore(),
        llm_config=llm_config,
        agent_type=AgentType.GENERAL,
        tool_args=payload.tool_args,
        workspace_manager=workspace_manager,
        skill_creator=skill_creator,
        connector_tool=connector_tool,
    )

    if payload.stream:
        # Return streaming response
        return StreamingResponse(
            _stream_events_as_sse(
                agent=agent,
                payload=payload,
                session_id=str(session_info.id),
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        run_output: RunOutput = await agent.arun(payload.message, stream=False)

        return TestAgentResponse(
            session_id=str(session_info.id),
            run_id=run_output.run_id,
            run_output=run_output.to_dict(),
        )


@router.post("/hitl", response_model=None)
async def test_agent_hitl_endpoint(
    payload: TestAgentPayload,
    current_user: CurrentUser,
    db: DBSession,
    settings: SettingsDep,
) -> StreamingResponse:
    """Test endpoint for Human-in-the-Loop (HITL) agent with tools requiring user input.

    This endpoint creates an IIAgent with a tool (send_email) that requires user input.
    When the tool is called, the run will pause and wait for user input via the continue endpoint.

    Events emitted:
    - RunStarted: When the run begins
    - RunContent: Content chunks as they are generated
    - ToolCallStarted: When a tool call begins
    - ToolCallPaused: When a tool requires user input
    - ToolCallCompleted: When a tool call finishes
    - RunCompleted: Final response with full content
    - error: If an error occurs
    - done: Final event indicating stream end

    Args:
        payload: Request payload with message, optional model_id and session_id

    Returns:
        StreamingResponse with SSE formatted events (stream-only)
    """
    # Create or get session
    session_service = SessionService(
        config=settings,
        session_repo=SessionRepository(),
        event_repo=EventRepository(),
        agent_run_service=AgentRunService(repo=AgentRunTaskRepository(), config=settings),
        file_store=storage,
        sandbox_repo=SandboxRepository(),
    )
    session_info = await session_service.get_or_create_session(
        db,
        session_uuid=str(payload.session_id) if payload.session_id else None,
        user_id=current_user.id,
    )

    llm_config: LLMConfig = await LLMSettingService(
        config=settings, repo=LLMSettingRepository(), session_repo=SessionRepository()
    ).get_llm_settings(
        db,
        session=session_info,
        source=payload.source,
        model_id=payload.model_id,
    )

    workspace_path = Path(settings.workspace_path).resolve()
    workspace_manager = WorkspaceManager(
        root=workspace_path,
        container_workspace=settings.use_container_workspace,
    )

    # Load user connectors (e.g., GitHub)
    from ii_agent.engine.v1.tools.connector import ConnectorTool

    connector_tool = ConnectorTool(user_id=current_user.id)

    agent = await _agent_factory.create_agent(
        session_id=str(session_info.id),
        user_id=current_user.id,
        session_store=AgentSessionStore(),
        llm_config=llm_config,
        agent_type=AgentType.GENERAL,
        tool_args=payload.tool_args,
        workspace_manager=workspace_manager,
        connector_tool=connector_tool,
    )

    # Add HITL tool to agent
    agent.add_tool(send_email)

    # Return streaming response
    return StreamingResponse(
        _stream_events_as_sse(
            event_stream=agent.arun(
                run_id=str(uuid4()), input=payload.message, stream=True, stream_events=True
            ),
            session_id=str(session_info.id),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _stream_continue_run_response(
    agent: IIAgent, run_response: RunOutput, session_id: str, continue_run: bool = False
) -> AsyncIterator[str]:
    """Async generator that yields SSE formatted events from continuing a paused run.

    Args:
        agent: The IIAgent instance
        run_response: The paused run response with updated tools
        session_id: Session ID for the run
        continue_run: If True, use acontinue_run; if False, use arun with run_response

    Yields:
        SSE formatted strings with event data
    """
    run_id = run_response.run_id

    # Create appropriate event stream based on continue_run flag
    if continue_run:
        event_stream = await agent.acontinue_run(  # type: ignore
            run_id=run_id,
            updated_tools=run_response.tools,
            stream=True,
            stream_events=True,
        )
    else:
        # Continue the run with updated tools using arun
        event_stream = agent.arun(
            message="",  # Empty message to continue from paused state
            stream=True,
            stream_events=True,
            run_response=run_response,
        )

    # Use unified SSE streamer
    async for sse_event in _stream_events_as_sse(
        event_stream=event_stream,
        session_id=session_id,
        run_id=run_id,
    ):
        yield sse_event


@router.post("/continue", response_model=None)
async def continue_paused_run_endpoint(
    payload: ContinueRunPayload,
    current_user: CurrentUser,
    db: DBSession,
    settings: SettingsDep,
) -> StreamingResponse:
    """Continue a paused run with user input (Human-in-the-Loop).

    This endpoint allows continuing a run that was paused due to requiring user input.
    The user provides input values for the required fields, and the run continues execution.

    Events emitted:
    - RunStarted: When the run resumes
    - RunContent: Content chunks as they are generated
    - ToolCallStarted: When a tool call begins
    - ToolCallCompleted: When a tool call finishes
    - RunCompleted: Final response with full content
    - error: If an error occurs
    - done: Final event indicating stream end

    Args:
        payload: Request payload with run_id, session_id, and user_input

    Returns:
        StreamingResponse with SSE formatted events (stream-only)
    """
    # Verify session belongs to user
    session_service = SessionService(
        config=settings,
        session_repo=SessionRepository(),
        event_repo=EventRepository(),
        agent_run_service=AgentRunService(repo=AgentRunTaskRepository(), config=settings),
        file_store=storage,
        sandbox_repo=SandboxRepository(),
    )
    session_info = await session_service.get_or_create_session(
        db,
        session_uuid=str(payload.session_id),
        user_id=current_user.id,
    )

    llm_config: LLMConfig = await LLMSettingService(
        config=settings, repo=LLMSettingRepository(), session_repo=SessionRepository()
    ).get_llm_settings(
        db,
        session=session_info,
        source=payload.source,
        model_id=payload.model_id,
    )

    workspace_path = Path(settings.workspace_path).resolve()
    workspace_manager = WorkspaceManager(
        root=workspace_path,
        container_workspace=settings.use_container_workspace,
    )

    session_store = AgentSessionStore()
    # Create agent with same session
    agent = await _agent_factory.create_agent(
        session_id=str(session_info.id),
        user_id=current_user.id,
        session_store=session_store,
        llm_config=llm_config,
        agent_type=session_info.agent_type or AgentType.GENERAL,
        tool_args={},
        workspace_manager=workspace_manager,
    )

    run_response = await session_store.get_by_run_id(
        run_id=payload.run_id, session_id=payload.session_id
    )
    if not run_response:
        raise ValueError(f"Run {payload.run_id} not found!")

    for requirement in run_response.active_requirements:
        if requirement.needs_confirmation:
            if payload.is_confirmed:
                requirement.confirm()
            else:
                requirement.reject()

    return StreamingResponse(
        _stream_continue_run_response(
            agent=agent,
            run_response=run_response,
            session_id=str(session_info.id),
            continue_run=True,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/session-summary", response_model=SessionSummaryResponse)
async def test_session_summary_endpoint(
    payload: SessionSummaryPayload,
    current_user: CurrentUser,
    db: DBSession,
    settings: SettingsDep,
) -> SessionSummaryResponse:
    """Test endpoint for generating session summary.

    This endpoint creates a summary of the conversation history for a given session.
    It uses the SessionSummaryManager to generate a summary based on all runs in the session.

    Args:
        payload: Request payload with session_id and optional model_id

    Returns:
        SessionSummaryResponse with the generated summary and topics
    """
    # Verify session belongs to user and get session info
    session_info = await SessionService(
        config=settings,
        session_repo=SessionRepository(),
        event_repo=EventRepository(),
        agent_run_service=AgentRunService(repo=AgentRunTaskRepository(), config=settings),
        file_store=storage,
        sandbox_repo=SandboxRepository(),
    ).get_or_create_session(
        db,
        session_uuid=str(payload.session_id),
        user_id=current_user.id,
    )

    # Get LLM config for the summary model
    llm_config: LLMConfig = await LLMSettingService(
        config=settings, repo=LLMSettingRepository(), session_repo=SessionRepository()
    ).get_llm_settings(
        db,
        session=session_info,
        source=payload.source,
        model_id=payload.model_id,
    )

    # Create session store and get the agent session with history
    session_store = AgentSessionStore()
    agent_session = await session_store.get_session(
        session_id=str(session_info.id),
        user_id=current_user.id,
    )

    # Check if session has any runs to summarize
    if not agent_session.runs:
        return SessionSummaryResponse(
            session_id=str(session_info.id),
            summary=None,
            topics=None,
            error="No runs found in session to summarize",
        )

    # Create the model for summary generation using the same logic as agent factory
    provider = PROVIDER_SPEC_MAP.get(llm_config.api_type)
    summary_model = get_model(provider, llm_config=llm_config)

    # Create session summary manager and generate summary
    session_summary_manager = SessionSummaryManager(model=summary_model)

    try:
        session_summary = await session_summary_manager.acreate_session_summary(
            session=agent_session
        )

        if session_summary:
            return SessionSummaryResponse(
                session_id=str(session_info.id),
                summary=session_summary.content,
                topics=session_summary.topics,
            )
        else:
            return SessionSummaryResponse(
                session_id=str(session_info.id),
                summary=None,
                topics=None,
                error="Failed to generate session summary",
            )

    except Exception as e:
        return SessionSummaryResponse(
            session_id=str(session_info.id),
            summary=None,
            topics=None,
            error=f"Error generating session summary: {str(e)}",
        )
