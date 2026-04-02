"""Adapter bridging RealtimeEvent streams to A2A Task events."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from string import capwords

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

from ii_agent.realtime.events.models import EventType, RealtimeEvent

logger = logging.getLogger("a2a_agent")

__all__ = ["EventStreamAdapter"]


class EventStreamAdapter:
    """Adapter to make A2A EventQueue compatible with our EventStream interface."""

    _WORKING_STATUS_EVENTS = {
        EventType.CONNECTION_ESTABLISHED,
        EventType.STATUS_UPDATE,
        EventType.AGENT_INITIALIZED,
        EventType.WORKSPACE_INFO,
        EventType.SANDBOX_STATUS,
        EventType.PROCESSING,
    }

    _COMPLETION_EVENTS = {
        EventType.STREAM_COMPLETE,
        EventType.COMPLETE,
    }

    _SUB_AGENT_SIGNALS = {EventType.SUB_AGENT_COMPLETE}

    _ARTIFACT_EVENTS = {
        EventType.AGENT_THINKING,
        EventType.TOOL_CALL,
        EventType.TOOL_RESULT,
        EventType.TOOL_CONFIRMATION,
        EventType.AGENT_RESPONSE,
        EventType.METRICS_UPDATE,
        EventType.PROMPT_GENERATED,
        EventType.USER_MESSAGE,
        EventType.FILE_EDIT,
        EventType.UPLOAD_SUCCESS,
        EventType.BROWSER_USE,
    }

    _STREAMING_ARTIFACT_EVENTS = {
        EventType.AGENT_RESPONSE,
        EventType.AGENT_THINKING,
        EventType.TOOL_RESULT,
    }

    def __init__(
        self,
        event_queue,
        context_id: Optional[str] = None,
        task_id: Optional[str] = None,
        runtime_trace_enabled: bool = False,
    ):
        self.event_queue = event_queue
        self.context_id = context_id
        self.task_id = task_id
        self._runtime_trace_enabled = runtime_trace_enabled
        self._artifact_sequence = 0
        self._artifact_streams: dict[str, str] = {}

    async def publish(self, event: RealtimeEvent) -> None:
        """Compatibility shim to satisfy EventStream interface."""
        await self.add_event(event)

    def subscribe(self, subscriber) -> None:  # pragma: no cover - optional
        """No-op subscription hook for interface compatibility."""
        return None

    def unsubscribe(self, subscriber) -> None:  # pragma: no cover - optional
        """No-op unsubscription hook for interface compatibility."""
        return None

    async def add_event(self, event: RealtimeEvent) -> None:
        """Add an event to the queue using the A2A EventQueue interface."""
        if not self.event_queue:
            return

        try:
            for a2a_event in self._convert_event(event):
                await self.event_queue.enqueue_event(a2a_event)
        except Exception as exc:
            logger.warning(
                "Failed to translate realtime event %s to A2A event: %s",
                event.type,
                exc,
                exc_info=True,
            )

    async def send(self, event: str, data: Any, content_type: str = "text/plain"):
        """Send event through A2A EventQueue."""
        if self.event_queue:
            try:
                artifact_event = TaskArtifactUpdateEvent(
                    context_id=self._context_id,
                    task_id=self._task_id,
                    artifact=new_text_artifact(
                        name="progress", text=f"{event}: {data}"
                    ),
                    append=False,
                )

                await self.event_queue.enqueue_event(artifact_event)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("Failed to send event through A2A queue: %s", e)

    @property
    def _context_id(self) -> str:
        """Return safe context id for outbound events."""
        return self.context_id or "unknown_context"

    @property
    def _task_id(self) -> str:
        """Return safe task id for outbound events."""
        return self.task_id or "unknown_task"

    def _convert_event(self, event: RealtimeEvent) -> list[Any]:
        """Convert internal realtime events to A2A protocol events."""
        if event.type in self._WORKING_STATUS_EVENTS:
            return self._status_working(event)
        if event.type in self._COMPLETION_EVENTS:
            return self._status_complete(event)
        if event.type in self._SUB_AGENT_SIGNALS:
            return self._status_sub_agent(event)
        if event.type == EventType.AGENT_RESPONSE_INTERRUPTED:
            return self._status_input_required(event)
        if event.type == EventType.ERROR:
            return self._status_failed(event)
        if event.type in self._ARTIFACT_EVENTS:
            return self._artifact_update(event)
        return self._artifact_update(event)

    def _status_working(self, event: RealtimeEvent) -> list[TaskStatusUpdateEvent]:
        """Build a working status update."""
        metadata = self._merge_metadata(
            {"code": "working"}, self._metadata(event.content)
        )
        return [
            self._build_status_event(
                TaskState.working,
                text=self._summarize_content(event.content),
                final=False,
                metadata=metadata,
            )
        ]

    def _status_complete(self, event: RealtimeEvent) -> list[TaskStatusUpdateEvent]:
        """Build a completion status update."""
        metadata = self._merge_metadata(
            {"code": "completed"}, self._metadata(event.content)
        )
        self._reset_streams()
        return [
            self._build_status_event(
                TaskState.completed,
                text=self._summarize_content(event.content),
                final=True,
                metadata=metadata,
            )
        ]

    def _status_failed(self, event: RealtimeEvent) -> list[TaskStatusUpdateEvent]:
        """Build a failure status update."""
        summary = self._summarize_content(event.content) or "Unexpected error"
        metadata = self._merge_metadata(
            {"code": "runtime_error"}, self._metadata(event.content)
        )
        self._reset_streams()
        return [
            self._build_status_event(
                TaskState.failed,
                text=summary,
                final=True,
                metadata=metadata,
            )
        ]

    def _status_input_required(
        self, event: RealtimeEvent
    ) -> list[TaskStatusUpdateEvent]:
        """Build an input required status update."""
        metadata = self._merge_metadata(
            {"code": "input_required"}, self._metadata(event.content)
        )
        self._reset_streams()
        return [
            self._build_status_event(
                TaskState.input_required,
                text=self._summarize_content(event.content),
                final=False,
                metadata=metadata,
            )
        ]

    def _status_sub_agent(self, event: RealtimeEvent) -> list[TaskStatusUpdateEvent]:
        """Emit a non-final status update for sub agent signals."""
        metadata = self._merge_metadata(
            {"code": "sub_agent_completed"}, self._metadata(event.content)
        )
        return [
            self._build_status_event(
                TaskState.working,
                text=self._summarize_content(event.content) or "Sub agent completed",
                final=False,
                metadata=metadata,
            )
        ]

    def _artifact_update(self, event: RealtimeEvent) -> list[TaskArtifactUpdateEvent]:
        """Convert event content to an artifact update."""
        text = self._artifact_text(event)
        if not text:
            return []

        artifact = new_text_artifact(
            name=self._artifact_name(event),
            text=text,
        )

        stream_key = self._resolve_stream_key(event)
        append = False
        release_stream = False
        if stream_key:
            artifact_id = self._artifact_streams.get(stream_key)
            if artifact_id is None:
                artifact_id = str(uuid.uuid4())
                self._artifact_streams[stream_key] = artifact_id
            else:
                append = True
            artifact.artifact_id = artifact_id
            if isinstance(event.content, dict) and any(
                event.content.get(flag) for flag in ("last_chunk", "final", "is_final")
            ):
                release_stream = True

        metadata = self._metadata(event.content)
        if self._runtime_trace_enabled:
            sequence = self._next_sequence()
            structured: dict[str, Any] = {
                "event_type": event.type.value,
                "sequence": sequence,
            }
            if event.timestamp is not None:
                structured["timestamp"] = event.timestamp
            if metadata:
                structured["data"] = metadata
            metadata = structured

        event_payload = TaskArtifactUpdateEvent(
            context_id=self._context_id,
            task_id=self._task_id,
            artifact=artifact,
            append=append,
            metadata=metadata,
        )

        if stream_key and release_stream:
            self._artifact_streams.pop(stream_key, None)

        return [event_payload]

    def _artifact_text(self, event: RealtimeEvent) -> Optional[str]:
        """Resolve artifact text with special handling for tool outputs."""
        if event.type == EventType.TOOL_CALL:
            text = self._extract_tool_call_text(event.content)
            if text:
                return text
        if event.type == EventType.TOOL_RESULT:
            text = self._extract_tool_result_text(event.content)
            if text:
                return text
        return self._summarize_content(event.content)

    def _extract_tool_call_text(self, content: Any) -> Optional[str]:
        """Produce a short description for tool call events."""
        if not isinstance(content, dict):
            return None

        display_name = content.get("tool_display_name") or content.get("tool_name")
        if not isinstance(display_name, str) or not display_name:
            display_name = "tool"

        action = "Calling"
        tool_input = content.get("tool_input")
        if isinstance(tool_input, dict):
            input_type = tool_input.get("type")
            if isinstance(input_type, str) and input_type:
                action = f"Calling {display_name} ({input_type})"
            else:
                action = f"Calling {display_name}"
        else:
            action = f"Calling {display_name}"

        return action

    def _extract_tool_result_text(self, content: Any) -> Optional[str]:
        """Extract user-facing text from message/message_user tool results."""
        if not isinstance(content, dict):
            return None

        tool_name = content.get("tool_name")
        if not isinstance(tool_name, str) or tool_name.lower() not in {
            "message",
            "message_user",
        }:
            return None

        result = content.get("result")
        text = self._extract_text_payload(result)
        if text:
            return text

        tool_input = content.get("tool_input")
        if isinstance(tool_input, dict):
            candidate = tool_input.get("message")
            if isinstance(candidate, str) and candidate:
                return candidate

        return None

    def _extract_text_payload(self, payload: Any) -> Optional[str]:
        """Return the first textual field inside a payload structure."""
        if isinstance(payload, str) and payload:
            return payload

        if isinstance(payload, dict):
            direct = payload.get("text") or payload.get("message")
            if isinstance(direct, str) and direct:
                return direct

            action = payload.get("action")
        if isinstance(action, dict):
            action_text = action.get("text")
            if isinstance(action_text, str) and action_text:
                return action_text

        return None

    def _artifact_name(self, event: RealtimeEvent) -> str:
        """Return a human-readable artifact name."""
        value = event.type.value.replace("_", " ")
        return capwords(value)

    def _reset_streams(self) -> None:
        """Clear streaming artifact tracking state."""
        self._artifact_streams.clear()

    def _resolve_stream_key(self, event: RealtimeEvent) -> Optional[str]:
        """Return a stream key for events that should append to the same artifact."""
        if event.type not in self._STREAMING_ARTIFACT_EVENTS:
            return None

        if isinstance(event.content, dict):
            tool_name = event.content.get("tool_name")
            if tool_name:
                return f"{event.type.value}:{tool_name}"
            if event.content.get("stream_key"):
                return str(event.content["stream_key"])

        return event.type.value

    def _metadata(self, content: Any) -> Optional[dict[str, Any]]:
        if isinstance(content, dict):
            return {k: v for k, v in content.items() if v is not None}
        return None

    def _merge_metadata(
        self, base: dict[str, Any], extra: Optional[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        if not base and not extra:
            return None
        merged = dict(base)
        if extra:
            merged.update(extra)
        return merged

    def _build_status_event(
        self,
        state: TaskState,
        *,
        text: Optional[str],
        final: bool,
        metadata: Optional[dict[str, Any]] = None,
    ) -> TaskStatusUpdateEvent:
        message = self._build_message(text) if text else None
        return TaskStatusUpdateEvent(
            context_id=self._context_id,
            task_id=self._task_id,
            status=TaskStatus(
                state=state,
                timestamp=datetime.now(timezone.utc).isoformat(),
                message=message,
            ),
            final=final,
            metadata=metadata,
        )

    def _summarize_content(self, content: Any) -> Optional[str]:
        if content is None:
            return None
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            if isinstance(content.get("text"), str):
                return content["text"]
            if isinstance(content.get("message"), str):
                return content["message"]
            if isinstance(content.get("detail"), str):
                return content["detail"]
            if isinstance(content.get("status"), str):
                return content["status"]
            try:
                return json.dumps(content, ensure_ascii=False)
            except (TypeError, ValueError):
                return str(content)
        return str(content)

    def _next_sequence(self) -> int:
        self._artifact_sequence += 1
        return self._artifact_sequence

    def _build_message(self, text: str) -> Message:
        """Create a standard A2A message encapsulating text."""
        return Message(
            message_id=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=text))],
            context_id=self.context_id,
            task_id=self.task_id,
        )

    @staticmethod
    def _metadata(content: Any) -> Optional[dict[str, Any]]:
        if isinstance(content, dict):
            return {k: v for k, v in content.items() if v is not None}
        return None
