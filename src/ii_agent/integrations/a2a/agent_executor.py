"""A2A Agent Executor implementation for II Agent platform."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from a2a.utils import new_text_artifact
from typing_extensions import override

from ii_agent.integrations.a2a.as_server import IIAgentA2AServer
from ii_agent.integrations.a2a.constants import (
    RUNTIME_TRACE_ARTIFACT_NAMES,
    RUNTIME_TRACE_EVENT_TYPES,
    SANDBOX_REUSE_EXTENSION_URI,
    SESSION_CONTEXT_EXTENSION_URI,
    SUPPORTED_EXTENSION_URIS,
    USER_AUTH_HANDOFF_EXTENSION_URI,
    RUNTIME_TRACE_EXTENSION_URI,
)
from ii_agent.integrations.a2a.context_adapter import A2ARequestPayload, extract_request_payload
from ii_agent.integrations.a2a.extension_utils import (
    append_extension_issue,
    collect_requested_extensions,
)

logger = logging.getLogger("a2a_executor")


class IIAgentExecutor(AgentExecutor):
    """A2A Agent Executor for II Agent platform."""

    def __init__(self):
        self.agent = IIAgentA2AServer()
        self._agent_service  = None
        logger.debug("II Agent Executor initialized")

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute the A2A request using II Agent services."""
        extension_info: Dict[str, Any] = {}
        try:

            def _truncate_for_log(text: Optional[str], *, limit: int = 800) -> str:
                if not text:
                    return ""
                trimmed = text.strip()
                if len(trimmed) <= limit:
                    return trimmed
                return f"{trimmed[:limit]}... [truncated {len(trimmed) - limit} chars]"

            logger.info(f"A2A Executor starting task {context.task_id}")

            query = context.get_user_input()
            if not query:
                raise Exception("No user input provided in request context")
            logger.info(
                "[A2A Task %s] Incoming user message: %s",
                context.task_id,
                _truncate_for_log(query),
            )

            try:
                request_payload = extract_request_payload(context)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Failed to extract A2A request payload: %s", exc, exc_info=True
                )
                request_payload = A2ARequestPayload()

            requested_extensions = self._resolve_requested_extensions(context)
            extension_info = self._prepare_extension_context(
                requested_extensions, request_payload
            )
            for uri in extension_info.get("active", []):
                context.add_activated_extension(uri)
            if extension_info.get("unsupported"):
                logger.warning(
                    "Unsupported A2A extensions requested: %s",
                    extension_info["unsupported"],
                )

            logger.debug(f"Processing request: {query[:50]}...")

            try:
                await self._emit_status_update(
                    event_queue=event_queue,
                    context_id=context.context_id,
                    task_id=context.task_id,
                    state=TaskState.working,
                    text=f"Request received. Starting processing...\n\n{query[:200]}",
                    final=False,
                    metadata=self._with_extension_metadata(
                        {"code": "processing", "progress": 0}, extension_info
                    ),
                )
            except Exception as e:
                logger.warning(f"Failed to send acknowledgment: {e}")

            if not context.context_id or not context.task_id:
                raise ValueError("A2A context_id and task_id are required.")

            # Process the request with event-driven handling
            logger.debug("Starting agent processing...")

            await self.agent.process_request(
                query,
                request_payload,
                a2a_context=context,
                event_queue=event_queue,
                extension_context=extension_info,
            )

        except Exception as e:
            logger.error(f"[A2A] Error in execute: {e}", exc_info=True)
            try:
                await self._emit_status_update(
                    event_queue=event_queue,
                    context_id=context.context_id,
                    task_id=context.task_id,
                    state=TaskState.failed,
                    text=str(e),
                    final=True,
                    metadata=self._with_extension_metadata(
                        {
                            "code": "agent_error",
                            "detail": str(e),
                            "origin": "ii-agent",
                        },
                        extension_info,
                    ),
                )

                error_message = self._build_message(
                    context_id=context.context_id,
                    task_id=context.task_id,
                    text=f"Error: {str(e)}",
                )
                error_message.metadata = self._with_extension_metadata(
                    {}, extension_info
                )

                await event_queue.enqueue_event(error_message)
                logger.debug("Error message sent successfully")

            except Exception as e2:
                logger.error(f"Failed to send error message: {e2}")

        logger.debug("A2A Executor request processing completed")

    @override
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel the current task."""
        logger.info(f"Cancelling task {context.task_id}")

        cancel_artifact = new_text_artifact(
            name="cancelled", text=f"Task {context.task_id} was cancelled."
        )
        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                context_id=context.context_id,
                task_id=context.task_id,
                artifact=cancel_artifact,
                kind="artifact-update",
            )
        )

    async def _emit_status_update(
        self,
        *,
        event_queue: EventQueue,
        context_id: str,
        task_id: str,
        state: TaskState,
        text: str,
        final: bool,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit a TaskStatusUpdateEvent with standardized payload."""

        message = self._build_message(context_id=context_id, task_id=task_id, text=text)

        status_event = TaskStatusUpdateEvent(
            context_id=context_id,
            task_id=task_id,
            status=TaskStatus(
                state=state,
                message=message,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
            final=final,
            kind="status-update",
            metadata=metadata,
        )

        await event_queue.enqueue_event(status_event)

    @staticmethod
    def _build_message(*, context_id: str, task_id: str, text: str) -> Message:
        """Create a standard Message payload."""

        return Message(
            message_id=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=text))],
            context_id=context_id,
            task_id=task_id,
        )

    @staticmethod
    def _build_completion_metadata(
        event: Dict[str, Any], extension_info: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Return structured metadata for completion events."""

        metadata: Dict[str, Any] = {
            "code": "completed",
            "progress": event.get("progress", 100),
        }

        result_data = event.get("result_data")
        if isinstance(result_data, dict):
            metadata["result"] = result_data

        return IIAgentExecutor._with_extension_metadata(metadata, extension_info)

    @staticmethod
    def _prepare_extension_context(
        requested_extensions: set[str], request_payload: A2ARequestPayload
    ) -> Dict[str, Any]:
        """Summarize requested and supported extensions for downstream metadata."""

        requested = set(requested_extensions or set())
        active = sorted(requested & SUPPORTED_EXTENSION_URIS)
        unsupported = sorted(requested - SUPPORTED_EXTENSION_URIS)

        context: Dict[str, Any] = {}
        if requested:
            context["requested"] = sorted(requested)
        if active:
            context["active"] = active
        if unsupported:
            context["unsupported"] = unsupported
            for uri in unsupported:
                append_extension_issue(
                    context,
                    uri=uri,
                    code="unsupported_extension",
                    detail="Extension not implemented by ii-agent",
                )

        if SESSION_CONTEXT_EXTENSION_URI in active:
            try:
                context["session_context"] = {
                    "metadata_keys": sorted(request_payload.metadata.keys())
                    if request_payload.metadata
                    else [],
                    "has_tool_args": bool(request_payload.tool_args),
                    "has_configuration": bool(request_payload.configuration),
                }
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Failed to summarize session-context extension payload: %s",
                    exc,
                    exc_info=True,
                )
                append_extension_issue(
                    context,
                    uri=SESSION_CONTEXT_EXTENSION_URI,
                    code="extension_processing_error",
                    detail=str(exc),
                )
        if SANDBOX_REUSE_EXTENSION_URI in active:
            try:
                sandbox = request_payload.sandbox
                sandbox_info: Dict[str, Any] = {
                    "reuse": sandbox.reuse,
                    "timeout_seconds": sandbox.timeout_seconds,
                    "has_sandbox_id": bool(sandbox.sandbox_id),
                    "has_template_id": bool(sandbox.template_id),
                }
                if sandbox.extra:
                    sandbox_info["extra_keys"] = sorted(sandbox.extra.keys())
                context["sandbox_reuse"] = sandbox_info
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Failed to summarize sandbox-reuse extension payload: %s",
                    exc,
                    exc_info=True,
                )
                append_extension_issue(
                    context,
                    uri=SANDBOX_REUSE_EXTENSION_URI,
                    code="extension_processing_error",
                    detail=str(exc),
                )
        if USER_AUTH_HANDOFF_EXTENSION_URI in active:
            try:
                user = request_payload.user
                user_info: Dict[str, Any] = {
                    "has_user_id": bool(user.user_id),
                    "has_api_key": bool(user.api_key),
                }
                if user.extra:
                    user_info["extra_keys"] = sorted(user.extra.keys())
                context["user_auth"] = user_info
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Failed to summarize user-auth extension payload: %s",
                    exc,
                    exc_info=True,
                )
                append_extension_issue(
                    context,
                    uri=USER_AUTH_HANDOFF_EXTENSION_URI,
                    code="extension_processing_error",
                    detail=str(exc),
                )
        if RUNTIME_TRACE_EXTENSION_URI in active:
            try:
                context["runtime_trace"] = {
                    "artifact_names": RUNTIME_TRACE_ARTIFACT_NAMES,
                    "event_types": RUNTIME_TRACE_EVENT_TYPES,
                    "metadata_fields": [
                        "event_type",
                        "sequence",
                        "timestamp",
                        "data",
                    ],
                }
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Failed to summarize runtime-trace extension payload: %s",
                    exc,
                    exc_info=True,
                )
                append_extension_issue(
                    context,
                    uri=RUNTIME_TRACE_EXTENSION_URI,
                    code="extension_processing_error",
                    detail=str(exc),
                )

        return context

    @staticmethod
    def _resolve_requested_extensions(context: RequestContext) -> set[str]:
        """Safely extract requested extensions from the call context."""

        try:
            return collect_requested_extensions(context)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(
                "Failed to aggregate requested extensions from %s: %s",
                type(context).__name__,
                exc,
                exc_info=True,
            )
            return set()

    @staticmethod
    def _with_extension_metadata(
        base: Optional[Dict[str, Any]], extension_info: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Attach extension metadata when available."""

        base_metadata = dict(base) if base else {}
        payload = {key: value for key, value in extension_info.items() if value}
        if payload:
            base_metadata["extensions"] = payload
        if base_metadata:
            return base_metadata
        return None
