"""Chat API router with SSE streaming support."""

import json
import logging
from typing import Optional
from uuid import UUID
import uuid

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ii_agent.auth.dependencies import DBSession, CurrentUser
from ii_agent.core.exceptions import InternalError, PaymentRequiredError
from ii_agent.chat.api.dependencies import ChatServiceDep
from ii_agent.chat.api.schemas import (
    ChatMessageRequest,
    MessageHistoryResponse,
    ClearHistoryResponse,
    StopConversationResponse,
    AdvancedModeState,
    AdvancedModeUpdateRequest,
)
from ii_agent.chat.media import MediaOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/chat", tags=["chat"])


@router.get(
    "/conversations/{session_id}/advanced-mode",
    response_model=AdvancedModeState,
)
async def get_advanced_mode_settings(
    session_id: str,
    current_user: CurrentUser,
    db_session: DBSession,
    chat_service: ChatServiceDep,
):
    """Return advanced mode state for a conversation."""
    await chat_service.validate_session_access(
        db_session,
        session_id=session_id,
        user_id=str(current_user.id),
    )
    return await MediaOrchestrator.get_advanced_mode_state(
        db_session=db_session,
        session_id=session_id,
        user_id=str(current_user.id),
    )


@router.post(
    "/conversations/{session_id}/advanced-mode",
    response_model=AdvancedModeState,
)
async def update_advanced_mode_settings(
    session_id: str,
    request: AdvancedModeUpdateRequest,
    current_user: CurrentUser,
    db_session: DBSession,
    chat_service: ChatServiceDep,
):
    """Persist advanced mode enablement and references."""
    await chat_service.validate_session_access(
        db_session,
        session_id=session_id,
        user_id=str(current_user.id),
    )
    return await MediaOrchestrator.update_advanced_mode_state(
        db_session=db_session,
        session_id=session_id,
        user_id=str(current_user.id),
        enabled=request.enabled,
        references=request.references,
    )


@router.post("/conversations")
async def send_chat_message(
    request: ChatMessageRequest,
    current_user: CurrentUser,
    db_session: DBSession,
    chat_service: ChatServiceDep,
):
    """
    Send a chat message with automatic session creation or reuse existing session.

    If request.session_id is provided, reuses that session.
    Otherwise, creates a new session automatically.

    Tool Support:
    - Provide tools parameter with granular control: {"web_search": true, "image_search": false}
    - Available tools: web_search, image_search, web_visit
    - Future tools: code_interpreter, file_search (coming soon)
    - LLM can call enabled tools as needed during conversation
    - Tool results are streamed back via tool_result events
    - Credits are deducted for both LLM usage and tool execution

    Returns SSE stream with event types:

    **Event: delta** (streaming content chunks)
    - delta_type: "content" | "reasoning"
    - data: string chunk

    **Event: message** (metadata and control events)
    - event: "session_created" - New session created (only if new session)
      - data: {session_id, name, status, agent_type, model_id, created_at}
    - event: "stream_start" - Message started
      - data: {session_id, model_id}
    - event: "tool_calls" - Tool/function calls
      - data: array of tool call objects
    - event: "function_call" - Legacy function call
      - data: {name, arguments}
    - event: "usage" - Token usage statistics
      - data: {completion_tokens, prompt_tokens, total_tokens, ...}
    - event: "stream_complete" - Stream finished
      - data: {message_id, message, usage, tokens, elapsed_ms}
    - event: "done" - All events sent
    - event: "error" - Error occurred
      - data: {error, code}

    **Event: tool_call** (tool invocation by LLM)
    - status: "start" - Tool call initiated
      - data: {id, name, type}
    - status: "delta" - Tool input streaming
      - data: {id, delta} (partial JSON)
    - status: "stop" - Tool call complete
      - data: {id, name, input} (complete JSON)

    **Event: tool_result** (tool execution result)
    - status: "info"
    - data: {tool_call_id, name, output, is_error}
    """

    # Validate model exists and is available
    await chat_service.validate_model_for_chat(
        db_session,
        model_id=request.model_id,
        user_id=str(current_user.id),
    )

    # Check credits
    has_credits = await chat_service.check_sufficient_credits(
        db_session,
        user_id=str(current_user.id)
    )
    if not has_credits:
        raise PaymentRequiredError("Insufficient credits")

    # Use existing session or create new one
    session_metadata = None
    session_id = None

    if request.session_id:
        # Use existing session
        session_id = str(request.session_id)

        # Validate user has access to this session
        await chat_service.validate_session_access(
            db_session,
            session_id=session_id,
            user_id=str(current_user.id),
        )
        logger.info(
            f"Reusing existing session {session_id} for user {current_user.id}"
        )
    else:
        # Create new session
        try:
            session_metadata = await chat_service.create_chat_session(
                db_session,
                user_id=str(current_user.id),
                user_message=request.content,
                model_id=request.model_id,
            )
            session_id = session_metadata.session_id
            request.session_id = uuid.UUID(session_id)
            logger.info(f"Created new session {session_id} for user {current_user.id}")

        except Exception as e:
            logger.error(f"Failed to create session: {e}", exc_info=True)
            raise InternalError("Failed to create session") from e

    async def event_generator():
        """Generate SSE events from provider stream following new SSE contract."""
        import time

        start_time = time.time()

        try:
            # Send session created event only if this is a new session
            if session_metadata:
                session_event = {
                    "status": "created",
                    "session_id": session_metadata.session_id,
                    "name": session_metadata.name,
                    "title_pending": session_metadata.title_pending,
                    "agent_type": session_metadata.agent_type,
                    "model_id": session_metadata.model_id,
                    "created_at": session_metadata.created_at,
                }
                yield f"event: session\ndata: {json.dumps(session_event)}\n\n"

            # Determine if this is a council request
            is_council = (
                request.council_preferences
                and request.council_preferences.enabled
            )

            if is_council:
                # Validate council config — reject invalid selections explicitly
                council_prefs = request.council_preferences
                if len(council_prefs.council_models) < 2:
                    yield f"event: error\ndata: {json.dumps({'message': 'Council mode requires at least 2 models'})}\n\n"
                    return
                if not council_prefs.synthesis_model_id:
                    yield f"event: error\ndata: {json.dumps({'message': 'Council mode requires a synthesis model'})}\n\n"
                    return

                stream = chat_service.stream_council_chat_response(
                    db_session,
                    chat_request=request,
                    user_id=str(current_user.id),
                )
            else:
                stream = chat_service.stream_chat_response(
                    db_session,
                    chat_request=request,
                    user_id=str(current_user.id),
                )

            # Stream response from provider
            async for event in stream:
                event_type = event.get("type")

                # Council member events
                if event_type in (
                    "council_member_start",
                    "council_member_delta",
                    "council_member_complete",
                    "council_member_error",
                ):
                    status = event_type.replace("council_member_", "")
                    council_event = {
                        "status": status,
                        "model_id": event.get("model_id"),
                        "model_name": event.get("model_name"),
                    }
                    if status == "delta":
                        council_event["delta"] = event.get("delta")
                    elif status == "complete":
                        council_event["content"] = event.get("content")
                    elif status == "error":
                        council_event["error"] = event.get("error")
                    yield f"event: council_member\ndata: {json.dumps(council_event)}\n\n"
                    continue

                # Council synthesis events
                elif event_type in (
                    "council_synthesis_start",
                    "council_synthesis_delta",
                    "council_synthesis_complete",
                    "council_synthesis_error",
                ):
                    status = event_type.replace("council_synthesis_", "")
                    synthesis_event = {
                        "status": status,
                        "model_id": event.get("model_id"),
                    }
                    if status == "delta":
                        synthesis_event["delta"] = event.get("delta")
                    elif status == "complete":
                        synthesis_event["content"] = event.get("content")
                    elif status == "error":
                        synthesis_event["error"] = event.get("error")
                    yield f"event: council_synthesis\ndata: {json.dumps(synthesis_event)}\n\n"
                    continue

                # Content events (start/delta/stop)
                if event_type == "content_start":
                    yield f"event: content\ndata: {json.dumps({'status': 'start'})}\n\n"

                elif event_type == "content_delta":
                    content_event = {"status": "delta", "delta": event.get("content")}
                    yield f"event: content\ndata: {json.dumps(content_event)}\n\n"

                elif event_type == "content_stop":
                    yield f"event: content\ndata: {json.dumps({'status': 'stop'})}\n\n"

                # Thinking events (delta-only, no start/stop)
                elif event_type == "thinking_delta":
                    thinking_event = {"status": "delta", "delta": event.get("thinking")}
                    # Include signature if present (for o1 models)
                    if event.get("signature"):
                        thinking_event["signature"] = event.get("signature")
                    yield f"event: thinking\ndata: {json.dumps(thinking_event)}\n\n"

                # Tool call events (start/delta/stop)
                elif event_type == "tool_use_start":
                    tool_call = event.get("tool_call", {})
                    tool_event = {
                        "status": "start",
                        "id": tool_call.id
                        if hasattr(tool_call, "id")
                        else tool_call.get("id"),
                        "name": tool_call.name
                        if hasattr(tool_call, "name")
                        else tool_call.get("name"),
                        "type": tool_call.type
                        if hasattr(tool_call, "type")
                        else tool_call.get("type", "function"),
                    }
                    yield f"event: tool_call\ndata: {json.dumps(tool_event)}\n\n"

                elif event_type == "tool_use_delta":
                    tool_call = event.get("tool_call", {})
                    tool_event = {
                        "status": "delta",
                        "id": tool_call.id
                        if hasattr(tool_call, "id")
                        else tool_call.get("id"),
                        "delta": tool_call.input
                        if hasattr(tool_call, "input")
                        else tool_call.get("input", ""),  # Partial JSON
                    }
                    yield f"event: tool_call\ndata: {json.dumps(tool_event)}\n\n"

                elif event_type == "tool_use_stop":
                    tool_call = event.get("tool_call", {})
                    tool_event = {
                        "status": "stop",
                        "id": tool_call.id
                        if hasattr(tool_call, "id")
                        else tool_call.get("id"),
                        "name": tool_call.name
                        if hasattr(tool_call, "name")
                        else tool_call.get("name"),
                        "input": tool_call.input
                        if hasattr(tool_call, "input")
                        else tool_call.get("input"),  # Complete JSON
                    }
                    yield f"event: tool_call\ndata: {json.dumps(tool_event)}\n\n"

                # Code interpreter events (start/delta/stop)
                elif event_type == "code_interpreter_start":
                    yield f"event: code_block\ndata: {json.dumps({'status': 'start'})}\n\n"

                elif event_type == "code_interpreter_delta":
                    ci_event = {"status": "delta", "delta": event.get("content")}
                    yield f"event: code_block\ndata: {json.dumps(ci_event)}\n\n"

                elif event_type == "code_interpreter_stop":
                    yield f"event: code_block\ndata: {json.dumps({'status': 'stop'})}\n\n"

                # Tool result events (from backend execution)
                elif event_type == "tool_progress":
                    progress_event = {
                        "status": "info",
                        "tool_call_id": event.get("tool_call_id"),
                        "name": event.get("name"),
                        "output": event.get("output"),
                    }
                    yield f"event: tool_progress\ndata: {json.dumps(progress_event)}\n\n"

                # Tool result events (from backend execution)
                elif event_type == "tool_result":
                    result_event = {
                        "status": "info",
                        "tool_call_id": event.get("tool_call_id"),
                        "name": event.get("name"),
                        "output": event.get("output"),
                        "is_error": event.get("is_error", False),
                    }
                    yield f"event: tool_result\ndata: {json.dumps(result_event)}\n\n"

                # Usage events (per LLM turn)
                elif event_type == "usage":
                    usage = event.get("usage", {})
                    usage_event = {
                        "status": "info",
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0),
                        "cache_creation_tokens": usage.get("cache_creation_tokens", 0),
                        "cache_read_tokens": usage.get("cache_read_tokens", 0),
                        "total_tokens": usage.get("input_tokens", 0)
                        + usage.get("output_tokens", 0),
                    }
                    yield f"event: usage\ndata: {json.dumps(usage_event)}\n\n"

                elif event_type == "error":
                    message = event.get("message") or event.get("error")
                    error_event = {
                        "status": "error",
                        "message": message,
                    }
                    if event.get("code"):
                        error_event["code"] = event.get("code")
                    yield f"event: error\ndata: {json.dumps(error_event)}\n\n"

                # Complete event (final - only sent when loop exits)
                elif event_type == "complete":
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    complete_event = {
                        "status": "done",
                        "message_id": str(event.get("message_id")),
                        "finish_reason": event.get("finish_reason", "end_turn"),
                        "elapsed_ms": elapsed_ms,
                        "files": event.get("files"),
                    }
                    yield f"event: complete\ndata: {json.dumps(complete_event)}\n\n"

        except Exception as e:
            logger.error(f"Chat streaming error: {e}", exc_info=True)
            error_event = {
                "status": "error",
                "message": str(e),
                "code": "streaming_error",
            }
            yield f"event: error\ndata: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post(
    "/conversations/{session_id}/stop", response_model=StopConversationResponse
)
async def stop_conversation(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    chat_service: ChatServiceDep,
) -> StopConversationResponse:
    """
    Stop an ongoing conversation by updating session status to 'pause'.

    Args:
        request: Stop conversation request with session_id
        current_user: Current authenticated user
        db_session: Database session

    Returns:
        StopConversationResponse with success status and last message ID
    """
    session_id = str(session_id)

    # Validate session access
    await chat_service.validate_session_access(
        db_session,
        session_id=session_id,
        user_id=str(current_user.id),
    )

    # Stop the conversation
    last_message_id = await chat_service.stop_conversation(
        db_session,
        session_id=session_id,
    )

    return StopConversationResponse(
        success=True,
        last_message_id=UUID(last_message_id) if last_message_id else None,
    )


@router.get("/conversations/{session_id}", response_model=MessageHistoryResponse)
async def get_message_history(
    session_id: str,
    current_user: CurrentUser,
    db_session: DBSession,
    chat_service: ChatServiceDep,
    limit: int = Query(50, ge=1, le=200),
    before: Optional[str] = None,
) -> MessageHistoryResponse:
    """Get conversation history for a session."""
    await chat_service.validate_session_access(
        db_session,
        session_id=session_id,
        user_id=str(current_user.id),
    )

    return await chat_service.build_message_history_response(
        db_session,
        session_id=session_id,
        limit=limit,
        before=before,
    )


@router.get("/conversations/{session_id}/public", response_model=MessageHistoryResponse)
async def get_public_message_history(
    session_id: str,
    db_session: DBSession,
    chat_service: ChatServiceDep,
    limit: int = Query(50, ge=1, le=200),
    before: Optional[str] = None,
) -> MessageHistoryResponse:
    """Get conversation history for a public session without authentication."""
    await chat_service.validate_public_session_access(
        db_session,
        session_id=session_id,
    )

    return await chat_service.build_message_history_response(
        db_session,
        session_id=session_id,
        limit=limit,
        before=before,
    )


@router.delete("/conversation/{session_id}", response_model=ClearHistoryResponse)
async def clear_conversation(
    session_id: str,
    current_user: CurrentUser,
    db_session: DBSession,
    chat_service: ChatServiceDep,
) -> ClearHistoryResponse:
    """Clear all messages in a conversation."""
    await chat_service.validate_session_access(
        db_session,
        session_id=session_id,
        user_id=str(current_user.id),
    )

    # Clear messages
    deleted_count = await chat_service.clear_messages(
        db_session,
        session_id=session_id
    )

    return ClearHistoryResponse(
        success=True,
        deleted_count=deleted_count,
        message="Conversation cleared successfully",
    )
