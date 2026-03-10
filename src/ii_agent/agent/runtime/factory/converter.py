"""Convert V1 agent events to RealtimeEvents for frontend compatibility."""

import uuid
from typing import Optional, Union
from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.agent.runs.models import RunStatus


from ii_agent.core.logger import logger
from ii_agent.agent.runtime.run.agent import (
    RunStartedEvent,
    RunContentEvent,
    RunContentDeltaEvent,
    RunContentCompletedEvent,
    RunCompletedEvent,
    RunErrorEvent,
    RunCancelledEvent,
    RunPausedEvent,
    RunContinuedEvent,
    ReasoningStartedEvent,
    ReasoningDeltaEvent,
    ReasoningCompletedEvent,
    SandboxInitializedEvent,
    ToolCallStartedEvent,
    ToolCallCompletedEvent,
    AgentSummaryStartedEvent,
    AgentSummaryCompletedEvent,
    RunOutput,
    RunOutputEvent,
)

def _get_sub_agent_info(event: Union[RunOutputEvent, RunOutput]) -> dict:
    """Extract sub-agent identification info from an event.

    Returns a dict with sub-agent fields if present, empty dict otherwise.
    """
    info = {}

    # Check for sub-agent identification fields
    if hasattr(event, "delegated_from") and event.delegated_from:
        info["delegated_from"] = event.delegated_from

    if hasattr(event, "is_sub_agent_event") and event.is_sub_agent_event:
        info["is_sub_agent_event"] = True

    if hasattr(event, "parent_run_id") and event.parent_run_id:
        info["parent_run_id"] = event.parent_run_id

    # For RunOutput, check is_sub_agent_response property
    if isinstance(event, RunOutput) and hasattr(event, "is_sub_agent_response"):
        if event.is_sub_agent_response:
            info["is_sub_agent_response"] = True
    # Include agent name for identification
    if hasattr(event, "agent_name") and event.agent_name:
        info["agent_name"] = event.agent_name

    return info


def convert_agent_event_to_realtime(
    event: Union[RunOutputEvent, RunOutput],
    session_id: str | uuid.UUID,
) -> Optional[RealtimeEvent]:
    """Convert a V1 agent event to a RealtimeEvent for frontend compatibility.

    Args:
        event: V1 agent event (RunOutputEvent or RunOutput)
        session_id: Session ID for the event

    Returns:
        RealtimeEvent or None if the event should be skipped
    """
    run_id = None
    if hasattr(event, "run_id") and event.run_id:
        try:
            run_id = uuid.UUID(event.run_id)
        except (ValueError, TypeError):
            run_id = None

    session_uuid = uuid.UUID(session_id) if isinstance(session_id, str) else session_id

    # Extract sub-agent identification info
    sub_agent_info = _get_sub_agent_info(event)

    # Extract origin event type
    origin = event.event if hasattr(event, "event") and event.event else RunOutput.__name__

    # RunOutput -> COMPLETE, SUB_AGENT_COMPLETE, or AGENT_RESPONSE_INTERRUPTED (if aborted)
    if isinstance(event, RunOutput):
        is_sub_agent = getattr(event, "is_sub_agent_response", False)
        status = getattr(event, "status", None)

        # If the run was aborted/cancelled, send interrupted event instead of complete
        if status == RunStatus.ABORTED:
            return RealtimeEvent(
                type=EventType.AGENT_RESPONSE_INTERRUPTED,
                session_id=session_uuid,
                run_id=uuid.UUID(event.run_id) if event.run_id else None,
                run_status=RunStatus.ABORTED if not is_sub_agent else None,
                content={
                    "origin": origin,
                    "message": getattr(event, "content", None) or "Run was cancelled",
                    "is_sub_agent_event": is_sub_agent,
                    **sub_agent_info,
                },
            )

        event_type = EventType.SUB_AGENT_COMPLETE if is_sub_agent else EventType.COMPLETE
        default_text = "Sub-agent completed" if is_sub_agent else "Task completed"
        return RealtimeEvent(
            type=event_type,
            session_id=session_uuid,
            run_id=uuid.UUID(event.run_id) if event.run_id else None,
            run_status=RunStatus.COMPLETED if not is_sub_agent else None,
            content={
                "origin": origin,
                "text": event.content or default_text,
                **sub_agent_info,
            },
        )

    # RunStartedEvent -> PROCESSING
    if isinstance(event, RunStartedEvent):
        is_sub_agent = bool(sub_agent_info)
        return RealtimeEvent(
            type=EventType.PROCESSING,
            session_id=session_uuid,
            run_id=run_id,
            run_status=RunStatus.RUNNING,
            content={
                "origin": origin,
                "message": "Processing your message...",
                "model": event.model,
                "model_provider": event.model_provider,
                "agent_name": event.agent_name,
                **sub_agent_info,
            },
        )

    # RunContentEvent -> AGENT_RESPONSE
    if isinstance(event, RunContentEvent):
        content_text = event.content
        return RealtimeEvent(
            type=EventType.AGENT_RESPONSE,
            session_id=session_uuid,
            run_id=run_id,
            content={
                "origin": origin,
                "text": content_text,
                "image": event.image,
                "citations": event.citations,
                **sub_agent_info,
            },
        )

    # RunCompletedEvent -> COMPLETE or SUB_AGENT_COMPLETE
    if isinstance(event, RunCompletedEvent):
        is_sub_agent = bool(
            sub_agent_info.get("is_sub_agent_event")
            or sub_agent_info.get("delegated_from")
            or sub_agent_info.get("parent_run_id")
            or sub_agent_info.get("is_sub_agent_response")
        )
        event_type = EventType.SUB_AGENT_COMPLETE if is_sub_agent else EventType.COMPLETE
        return RealtimeEvent(
            type=event_type,
            session_id=session_uuid,
            run_id=run_id,
            run_status=RunStatus.COMPLETED if not is_sub_agent else None,
            content={"origin": origin, **sub_agent_info},
        )

    # RunErrorEvent -> ERROR
    if isinstance(event, RunErrorEvent):
        return RealtimeEvent(
            type=EventType.ERROR,
            session_id=session_uuid,
            run_id=run_id,
            run_status=RunStatus.ERROR,
            content={
                "origin": origin,
                "message": event.content or "An error occurred",
                "error_type": event.error_type or "unknown",
                "error_id": event.error_id,
                "additional_data": event.additional_data,
                **sub_agent_info,
            },
        )

    # RunCancelledEvent -> AGENT_RESPONSE_INTERRUPTED
    if isinstance(event, RunCancelledEvent):
        return RealtimeEvent(
            type=EventType.AGENT_RESPONSE_INTERRUPTED,
            session_id=session_uuid,
            run_id=run_id,
            run_status=RunStatus.ABORTED,
            content={
                "origin": origin,
                "message": event.reason or "Agent run was cancelled",
                **sub_agent_info,
            },
        )

    # RunPausedEvent -> TOOL_CONFIRMATION (if tools require confirmation)
    if isinstance(event, RunPausedEvent):
        tools_data = []
        if event.tools:
            for tool in event.tools:
                tool_data = {
                    "tool_call_id": tool.tool_call_id if hasattr(tool, "tool_call_id") else None,
                    "tool_name": tool.tool_name if hasattr(tool, "tool_name") else None,
                    "tool_input": tool.tool_args if hasattr(tool, "tool_args") else None,
                    "requires_confirmation": tool.requires_confirmation
                    if hasattr(tool, "requires_confirmation")
                    else False,
                    "requires_user_input": tool.requires_user_input
                    if hasattr(tool, "requires_user_input")
                    else False,
                    "external_execution_required": tool.external_execution_required
                    if hasattr(tool, "external_execution_required")
                    else False,
                }

                # Include user input schema if present
                if hasattr(tool, "user_input_schema") and tool.user_input_schema:
                    tool_data["user_input_schema"] = [
                        field.to_dict() for field in tool.user_input_schema
                    ]

                tools_data.append(tool_data)

        # Build comprehensive requirements data
        requirements_data = []
        if event.requirements:
            for req in event.requirements:
                req_data = {
                    "id": getattr(req, "id", None),
                    "needs_confirmation": req.needs_confirmation,
                    "needs_user_input": req.needs_user_input,
                    "needs_external_execution": req.needs_external_execution,
                    "is_resolved": req.is_resolved(),
                }

                # Include tool execution details
                if req.tool_execution:
                    req_data["tool_execution"] = {
                        "tool_call_id": req.tool_execution.tool_call_id,
                        "tool_name": req.tool_execution.tool_name,
                        "tool_args": req.tool_execution.tool_args,
                        "requires_confirmation": req.tool_execution.requires_confirmation,
                        "requires_user_input": req.tool_execution.requires_user_input,
                        "external_execution_required": req.tool_execution.external_execution_required,
                    }

                    # Include user input schema if present
                    if req.tool_execution.user_input_schema:
                        req_data["tool_execution"]["user_input_schema"] = [
                            field.to_dict() for field in req.tool_execution.user_input_schema
                        ]

                requirements_data.append(req_data)

        # Get active (unresolved) requirements
        active_requirements = []
        if hasattr(event, "active_requirements"):
            for req in event.active_requirements:
                active_req_data = {
                    "id": getattr(req, "id", None),
                    "needs_confirmation": req.needs_confirmation,
                    "needs_user_input": req.needs_user_input,
                    "needs_external_execution": req.needs_external_execution,
                }

                if req.tool_execution:
                    active_req_data["tool_execution"] = {
                        "tool_call_id": req.tool_execution.tool_call_id,
                        "tool_name": req.tool_execution.tool_name,
                        "tool_args": req.tool_execution.tool_args,
                    }

                    # Include user input schema for active requirements
                    if req.tool_execution.user_input_schema:
                        active_req_data["user_input_schema"] = [
                            field.to_dict() for field in req.tool_execution.user_input_schema
                        ]

                active_requirements.append(active_req_data)

        return RealtimeEvent(
            type=EventType.TOOL_CONFIRMATION,
            session_id=session_uuid,
            run_id=run_id,
            run_status=RunStatus.PAUSED,
            content={
                "origin": origin,
                "message": "Agent is paused awaiting confirmation",
                "tools": tools_data,
                "requirements": requirements_data,
                "active_requirements": active_requirements,
                **sub_agent_info,
            },
        )

    # RunContinuedEvent -> PROCESSING
    if isinstance(event, RunContinuedEvent):
        return RealtimeEvent(
            type=EventType.PROCESSING,
            session_id=session_uuid,
            run_id=run_id,
            run_status=RunStatus.RUNNING,
            content={
                "origin": origin,
                "message": "Agent resumed processing...",
                **sub_agent_info,
            },
        )

    # ReasoningStartedEvent -> Skip (FE doesn't handle AGENT_THINKING_START;
    # the first AGENT_THINKING_DELTA implicitly starts the thinking UI)
    if isinstance(event, ReasoningStartedEvent):
        return RealtimeEvent(
            type=EventType.AGENT_THINKING_START,
            session_id=session_uuid,
            run_id=run_id,
            content={
                "origin": origin,
                **sub_agent_info,
            },
        )

    # ReasoningDeltaEvent -> AGENT_THINKING_DELTA (streaming reasoning tokens)
    if isinstance(event, ReasoningDeltaEvent):
        # Use redacted content if available, otherwise use regular content
        reasoning_text = event.redacted_reasoning_content if event.is_redacted else event.reasoning_content
        return RealtimeEvent(
            type=EventType.AGENT_THINKING_DELTA,
            session_id=session_uuid,
            run_id=run_id,
            content={
                "origin": origin,
                "text": reasoning_text or "",
                "is_redacted": event.is_redacted,
                **sub_agent_info,
            },
        )

    # RunContentDeltaEvent -> AGENT_RESPONSE_DELTA (streaming response tokens)
    if isinstance(event, RunContentDeltaEvent):
        return RealtimeEvent(
            type=EventType.AGENT_RESPONSE_DELTA,
            session_id=session_uuid,
            run_id=run_id,
            content={
                "origin": origin,
                "text": event.content or "",
                **sub_agent_info,
            },
        )


    # ReasoningCompletedEvent -> AGENT_THINKING
    if isinstance(event, ReasoningCompletedEvent):
        return RealtimeEvent(
            type=EventType.AGENT_THINKING,
            session_id=session_uuid,
            run_id=run_id,
            content={
                "origin": origin,
                "text": event.content,
                **sub_agent_info,
            },
        )


    if isinstance(event, SandboxInitializedEvent):
        return RealtimeEvent(
            type=EventType.SANDBOX_STATUS,
            session_id=session_uuid,
            run_id=run_id,
            content={
                "origin": origin,
                "status": event.sandbox_info.status if event.sandbox_info else None,
                "vscode_url": event.sandbox_info.vscode_url if event.sandbox_info else None,
                **sub_agent_info,
            },
        )

    # ToolCallStartedEvent -> TOOL_CALL
    if isinstance(event, ToolCallStartedEvent):
        tool = event.tool
        tool_data = {"origin": origin}
        if tool:
            tool_data.update({
                "tool_call_id": tool.tool_call_id if hasattr(tool, "tool_call_id") else None,
                "tool_name": tool.tool_name if hasattr(tool, "tool_name") else None,
                "tool_input": tool.tool_args if hasattr(tool, "tool_args") else None,
                "tool_display_name": tool.display_name if hasattr(tool, "display_name") and tool.display_name else tool.tool_name,
                "tool_logo": tool.tool_logo if hasattr(tool, "tool_logo") else None,
            })
        # Include sub-agent info in tool_data
        tool_data.update(sub_agent_info)
        return RealtimeEvent(
            type=EventType.TOOL_CALL,
            session_id=session_uuid,
            run_id=run_id,
            content=tool_data,
        )

    # ToolCallCompletedEvent -> TOOL_RESULT
    if isinstance(event, ToolCallCompletedEvent):
        from ii_agent.agent.runtime.tools.base import ToolResult as BaseToolResult

        tool = event.tool
        result_for_display = tool.result
        is_error = False
        tool_cost = 0.0

        # If result is a BaseToolResult, extract user_display_content for websocket display
        # user_display_content can be a string, dict, or list - pass it directly to frontend
        if isinstance(tool.result, BaseToolResult):
            is_error = tool.result.is_error or False
            tool_cost = tool.result.cost
            # Use user_display_content if available, otherwise fallback to llm_content
            if tool.result.user_display_content is not None:
                result_for_display = tool.result.user_display_content
            else:
                llm_content = tool.result.llm_content
                if isinstance(llm_content, str):
                    result_for_display = llm_content
                elif isinstance(llm_content, list):
                    # Convert content objects to dicts for JSON serialization
                    result_for_display = [
                        content.model_dump() if hasattr(content, "model_dump") else str(content)
                        for content in llm_content
                    ]
                else:
                    result_for_display = str(llm_content)

        tool_data = {
            "origin": origin,
            "result": result_for_display,
            "is_error": is_error,
            "cost": tool_cost,
        }
        if tool:
            tool_data.update(
                {
                    "tool_call_id": tool.tool_call_id if hasattr(tool, "tool_call_id") else None,
                    "tool_name": tool.tool_name if hasattr(tool, "tool_name") else None,
                    "tool_input": tool.tool_args if hasattr(tool, "tool_args") else None,
                    "tool_display_name": tool.display_name if hasattr(tool, "display_name") and tool.display_name else tool.tool_name,
                    "tool_logo": tool.tool_logo if hasattr(tool, "tool_logo") else None,
                }
            )
        # Include sub-agent info in tool_data
        tool_data.update(sub_agent_info)
        return RealtimeEvent(
            type=EventType.TOOL_RESULT,
            session_id=session_uuid,
            run_id=run_id,
            content=tool_data,
        )

    # AgentSummaryStartedEvent -> Skip (wait for completed event)
    if isinstance(event, AgentSummaryStartedEvent):
        return None

    # AgentSummaryCompletedEvent -> MODEL_COMPACT
    if isinstance(event, AgentSummaryCompletedEvent):
        summary_content = None
        if hasattr(event, "session_summary") and event.session_summary:
            summary_content = event.session_summary.content

        return RealtimeEvent(
            type=EventType.MODEL_COMPACT,
            session_id=session_uuid,
            run_id=run_id,
            content={
                "origin": origin,
                "status": "compacted",
                "summary": summary_content,
                **sub_agent_info,
            },
        )

    # For any unhandled event types, return None to skip
    return None
