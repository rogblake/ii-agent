from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import uuid
import asyncio

from ii_agent.core.db import get_db_session_local
from ii_agent.files.media import Audio, Image
from ii_agent.agents.models.message import Citations
from ii_agent.agents.models.response import ToolExecution
from ii_agent.agents.runs.agent import (
    MemoryUpdateCompletedEvent,
    MemoryUpdateStartedEvent,
    OutputModelResponseCompletedEvent,
    OutputModelResponseStartedEvent,
    ParserModelResponseCompletedEvent,
    ParserModelResponseStartedEvent,
    PostHookCompletedEvent,
    PostHookStartedEvent,
    PreHookCompletedEvent,
    PreHookStartedEvent,
    ReasoningCompletedEvent,
    ReasoningDeltaEvent,
    ReasoningStartedEvent,
    RunCancelledEvent,
    RunCompletedEvent,
    RunContentCompletedEvent,
    RunContentDeltaEvent,
    RunContentEvent,
    RunContinuedEvent,
    RunErrorEvent,
    RunEvent,
    RunInput,
    RunOutput,
    RunOutputEvent,
    RunPausedEvent,
    RunStartedEvent,
    SandboxInitializedEvent,
    AgentSummaryCompletedEvent,
    AgentSummaryStartedEvent,
    ToolCallCompletedEvent,
    ToolCallStartedEvent,
)
from ii_agent.agents.runs.requirement import RunRequirement
from ii_agent.agents.sandboxes.schemas import SandboxInfo
from ii_agent.agents.sessions.summary import AgentSummary

if TYPE_CHECKING:
    pass


def create_run_started_event(from_run_response: RunOutput) -> RunStartedEvent:
    return RunStartedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
    )


def create_run_completed_event(from_run_response: RunOutput) -> RunCompletedEvent:
    return RunCompletedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
        content=from_run_response.content,  # type: ignore
        content_type=from_run_response.content_type,  # type: ignore
        reasoning_content=from_run_response.reasoning_content,  # type: ignore
        citations=from_run_response.citations,  # type: ignore
        model_provider_data=from_run_response.model_provider_data,  # type: ignore
        images=from_run_response.images,  # type: ignore
        videos=from_run_response.videos,  # type: ignore
        audio=from_run_response.audio,  # type: ignore
        response_audio=from_run_response.response_audio,  # type: ignore
        references=from_run_response.references,  # type: ignore
        additional_input=from_run_response.additional_input,  # type: ignore
        reasoning_messages=from_run_response.reasoning_messages,  # type: ignore
        metadata=from_run_response.metadata,  # type: ignore
        metrics=from_run_response.metrics,  # type: ignore
        session_state=from_run_response.session_state,  # type: ignore
        status=from_run_response.status,  # type: ignore
    )


def create_run_paused_event(
    from_run_response: RunOutput,
    tools: Optional[List[ToolExecution]] = None,
    requirements: Optional[List[RunRequirement]] = None,
) -> RunPausedEvent:
    return RunPausedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
        tools=tools,
        requirements=requirements,
        content=from_run_response.content,
    )


def create_run_continued_event(from_run_response: RunOutput) -> RunContinuedEvent:
    return RunContinuedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
    )


def create_run_error_event(from_run_response: RunOutput, error: str) -> RunErrorEvent:
    return RunErrorEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
        content=error,
    )


def create_run_cancelled_event(from_run_response: RunOutput, reason: str) -> RunCancelledEvent:
    return RunCancelledEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
        reason=reason,
    )


def create_pre_hook_started_event(
    from_run_response: RunOutput,
    pre_hook_name: Optional[str] = None,
    run_input: Optional[RunInput] = None,
) -> PreHookStartedEvent:
    from copy import deepcopy

    return PreHookStartedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
        pre_hook_name=pre_hook_name,
        run_input=deepcopy(run_input),
    )


def create_pre_hook_completed_event(
    from_run_response: RunOutput,
    pre_hook_name: Optional[str] = None,
    run_input: Optional[RunInput] = None,
) -> PreHookCompletedEvent:
    from copy import deepcopy

    return PreHookCompletedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
        pre_hook_name=pre_hook_name,
        run_input=deepcopy(run_input),
    )


def create_post_hook_started_event(
    from_run_response: RunOutput, post_hook_name: Optional[str] = None
) -> PostHookStartedEvent:
    return PostHookStartedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
        post_hook_name=post_hook_name,
    )


def create_post_hook_completed_event(
    from_run_response: RunOutput, post_hook_name: Optional[str] = None
) -> PostHookCompletedEvent:
    return PostHookCompletedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
        post_hook_name=post_hook_name,
    )


def create_memory_update_started_event(
    from_run_response: RunOutput,
) -> MemoryUpdateStartedEvent:
    return MemoryUpdateStartedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
    )


def create_memory_update_completed_event(
    from_run_response: RunOutput,
) -> MemoryUpdateCompletedEvent:
    return MemoryUpdateCompletedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
    )


def create_session_summary_started_event(
    from_run_response: RunOutput,
) -> AgentSummaryStartedEvent:
    return AgentSummaryStartedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
    )


def create_session_summary_completed_event(
    from_run_response: RunOutput, session_summary: Optional[AgentSummary] = None
) -> AgentSummaryCompletedEvent:
    return AgentSummaryCompletedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
        session_summary=session_summary,
    )


def create_reasoning_started_event(
    from_run_response: RunOutput,
) -> ReasoningStartedEvent:
    return ReasoningStartedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
    )


def create_reasoning_delta_event(
    from_run_response: RunOutput,
    reasoning_content: Optional[str] = None,
    redacted_reasoning_content: Optional[str] = None,
    is_redacted: bool = False,
    provider_data: Optional[Dict[str, Any]] = None,
) -> ReasoningDeltaEvent:
    """Create a reasoning delta event for streaming reasoning/thinking content.

    Args:
        from_run_response: The current RunOutput
        reasoning_content: The reasoning content delta (chunk)
        redacted_reasoning_content: Redacted reasoning content (for models that support it)
        is_redacted: Whether the reasoning content is redacted/encrypted
        provider_data: Provider-specific metadata (e.g., signature for Anthropic)

    Returns:
        ReasoningDeltaEvent with the reasoning content
    """
    return ReasoningDeltaEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
        reasoning_content=reasoning_content,
        redacted_reasoning_content=redacted_reasoning_content,
        is_redacted=is_redacted,
        provider_data=provider_data,
    )


def create_reasoning_completed_event(
    from_run_response: RunOutput,
    content: Optional[Any] = None,
    content_type: Optional[str] = None,
    provider_data: Optional[Dict[str, Any]] = None,
) -> ReasoningCompletedEvent:
    """Create a reasoning completed event.

    Args:
        from_run_response: The current RunOutput
        content: The final reasoning content (summary or full)
        content_type: Type of the content (default: "str")
        provider_data: Provider-specific metadata for conversation continuity
                      (e.g., encrypted_content for OpenAI ZDR mode, signature for Anthropic)

    Returns:
        ReasoningCompletedEvent with the final reasoning content
    """
    return ReasoningCompletedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
        content=content,
        content_type=content_type or "str",
        provider_data=provider_data,
    )


def create_tool_call_started_event(
    from_run_response: RunOutput, tool: ToolExecution
) -> ToolCallStartedEvent:
    return ToolCallStartedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
        tool=tool,
    )


def create_tool_call_completed_event(
    from_run_response: RunOutput, tool: ToolExecution, content: Optional[Any] = None
) -> ToolCallCompletedEvent:
    return ToolCallCompletedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
        tool=tool,
        content=content,
        images=from_run_response.images,
        videos=from_run_response.videos,
        audio=from_run_response.audio,
    )


def create_sandbox_initialized_event(
    from_run_response: RunOutput,
    sandbox_info: SandboxInfo,
) -> SandboxInitializedEvent:
    return SandboxInitializedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
        sandbox_info=sandbox_info,
    )


def create_run_content_delta_event(
    from_run_response: RunOutput,
    content: Optional[Any] = None,
    content_type: Optional[str] = None,
) -> RunContentDeltaEvent:

    return RunContentDeltaEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
        content=content,
        content_type=content_type or "str",
    )


def create_run_output_content_event(
    from_run_response: RunOutput,
    content: Optional[Any] = None,
    content_type: Optional[str] = None,
    reasoning_content: Optional[str] = None,
    redacted_reasoning_content: Optional[str] = None,
    model_provider_data: Optional[Dict[str, Any]] = None,
    citations: Optional[Citations] = None,
    response_audio: Optional[Audio] = None,
    image: Optional[Image] = None,
) -> RunContentEvent:
    thinking_combined = (reasoning_content or "") + (redacted_reasoning_content or "")

    return RunContentEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
        content=content,
        content_type=content_type or "str",
        reasoning_content=thinking_combined,
        citations=citations,
        response_audio=response_audio,
        image=image,
        references=from_run_response.references,
        additional_input=from_run_response.additional_input,
        reasoning_messages=from_run_response.reasoning_messages,
        model_provider_data=model_provider_data,
    )


def create_run_content_completed_event(
    from_run_response: RunOutput,
) -> RunContentCompletedEvent:
    return RunContentCompletedEvent(
        content=from_run_response.content,
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
    )


def create_parser_model_response_started_event(
    from_run_response: RunOutput,
) -> ParserModelResponseStartedEvent:
    return ParserModelResponseStartedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
    )


def create_parser_model_response_completed_event(
    from_run_response: RunOutput,
) -> ParserModelResponseCompletedEvent:
    return ParserModelResponseCompletedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
    )


def create_output_model_response_started_event(
    from_run_response: RunOutput,
) -> OutputModelResponseStartedEvent:
    return OutputModelResponseStartedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
    )


def create_output_model_response_completed_event(
    from_run_response: RunOutput,
) -> OutputModelResponseCompletedEvent:
    return OutputModelResponseCompletedEvent(
        session_id=from_run_response.session_id,
        agent_id=from_run_response.agent_id,  # type: ignore
        agent_name=from_run_response.agent_name,  # type: ignore
        run_id=from_run_response.run_id,
        model=from_run_response.model,  # type: ignore
        model_provider=from_run_response.model_provider,  # type: ignore
    )


def handle_event(
    event: RunOutputEvent,
    run_response: RunOutput,
    events_to_skip: Optional[List[RunEvent]] = None,
    store_events: bool = False,
) -> RunOutputEvent:
    """Handle event storage and persistence."""

    return event
