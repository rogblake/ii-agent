"""Event collector for streaming agent events to MCP clients."""

import asyncio
import json
import logging
import time as time_module
import uuid
from typing import Any, Dict, Optional

import anyio
import socketio
from fastmcp import FastMCP
from mcp import types as mcp_types

from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.agent.events.repository import EventRepository
from ii_agent.agent.events.stream import EventHookRegistry

logger = logging.getLogger(__name__)


class MCPEventCollector:
    """Collects agent events and streams them to client via MCP notifications."""

    def __init__(
        self,
        mcp_server: Optional[FastMCP] = None,
        session_id: Optional[uuid.UUID] = None,
        sio: Optional[socketio.AsyncServer] = None,
    ):
        self._events: asyncio.Queue = asyncio.Queue()
        self._final_response: Optional[str] = None
        self._is_complete = False
        # Track tool calls and results for OpenAI format
        self._tool_calls: list[Dict[str, Any]] = []
        self._tool_results: list[Dict[str, Any]] = []
        self._pending_tool_calls: Dict[str, Dict[str, Any]] = {}  # tool_call_id -> tool_call
        # OpenAI messages list - built incrementally
        self._openai_messages: list[Dict[str, Any]] = []
        # MCP server for sending notifications
        self._mcp_server: Optional[FastMCP] = mcp_server
        self._event_count = 0
        self._hook_registry = EventHookRegistry()
        # Session ID for saving events to database
        self._session_id: Optional[uuid.UUID] = session_id
        # Socket.IO server for broadcasting to connected clients
        self._sio: Optional[socketio.AsyncServer] = sio

    async def publish(self, event: RealtimeEvent) -> None:
        """Capture events from the agent and stream to client."""
        try:
            processed_event = await self._hook_registry.process_event(event)
        except Exception as e:
            logger.error(f"Error processing event hooks: {e}")
            processed_event = event

        if processed_event is None:
            return

        event = processed_event
        await self._events.put(event)
        self._event_count += 1

        # Save event to database (skip USER_MESSAGE to avoid duplication)
        if self._session_id and event.type != EventType.USER_MESSAGE:
            try:
                from ii_agent.core.db.manager import get_db_session_local

                async with get_db_session_local() as db:
                    event_repo = EventRepository()
                    await event_repo.save(db, self._session_id, event)
            except Exception as e:
                logger.warning(f"Failed to save event to database: {e}")

        # Stream event to client via FastMCP Context
        await self._stream_event_to_client(event)

        # Broadcast event to Socket.IO room for web clients
        await self._emit_to_socketio(event)

        # Handle tool call events
        if event.type == EventType.TOOL_CALL:
            await self._handle_tool_call(event)

        # Handle tool result events
        elif event.type == EventType.TOOL_RESULT:
            await self._handle_tool_result(event)

        # Accumulate text from agent responses AND thinking events
        elif event.type in (EventType.AGENT_RESPONSE, EventType.AGENT_THINKING):
            if isinstance(event.content, dict):
                text = event.content.get("text", "")
                if text:
                    if self._final_response:
                        self._final_response += text
                    else:
                        self._final_response = text

        # Check for completion events
        if event.type in (EventType.COMPLETE, EventType.STREAM_COMPLETE):
            self._is_complete = True
            if not self._final_response:
                if isinstance(event.content, dict):
                    self._final_response = event.content.get("text") or event.content.get("message")
                elif isinstance(event.content, str):
                    self._final_response = event.content

    async def _handle_tool_call(self, event: RealtimeEvent) -> None:
        """Process tool call event and store in OpenAI format.

        Creates an assistant message with tool_calls in OpenAI format.
        """
        content = event.content
        if not isinstance(content, dict):
            return

        # Extract tool call information
        tool_call_id = content.get("tool_call_id") or content.get("id") or str(uuid.uuid4())
        tool_name = content.get("tool_name") or content.get("name", "unknown_tool")
        tool_input = content.get("tool_input") or content.get("input") or content.get("arguments", {})

        # Convert tool_input to JSON string if it's a dict
        if isinstance(tool_input, dict):
            arguments_str = json.dumps(tool_input)
        else:
            arguments_str = str(tool_input) if tool_input else "{}"

        # Create OpenAI format tool call
        tool_call = {
            "id": tool_call_id,
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": arguments_str,
            },
        }

        self._tool_calls.append(tool_call)
        self._pending_tool_calls[tool_call_id] = tool_call

        # Create assistant message with tool_calls in OpenAI format
        assistant_message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [tool_call],
        }
        self._openai_messages.append(assistant_message)

    async def _handle_tool_result(self, event: RealtimeEvent) -> None:
        """Process tool result event and store in OpenAI format.

        Creates a tool message with the result in OpenAI format.
        """
        content = event.content
        if not isinstance(content, dict):
            return

        # Extract tool result information
        tool_call_id = content.get("tool_call_id") or content.get("id")
        tool_name = content.get("tool_name") or content.get("name")
        result = content.get("result") or content.get("output") or content.get("content", "")

        # Handle fullstack_project_init: save preview_url to session
        if tool_name == "fullstack_project_init" and isinstance(result, dict):
            preview_url = result.get("preview_url")
            if preview_url and self._session_id:
                try:
                    from ii_agent.sessions.service import SessionService
                    from ii_agent.sessions.repository import SessionRepository
                    from ii_agent.agent.runs.service import AgentRunService
                    from ii_agent.agent.runs.repository import AgentRunTaskRepository
                    from ii_agent.agent.sandboxes.repository import SandboxRepository
                    from ii_agent.core.storage.client import storage
                    from ii_agent.core.config.settings import get_settings
                    from ii_agent.core.db.manager import get_db_session_local
                    _cfg = get_settings()
                    async with get_db_session_local() as db:
                        await SessionService(
                            config=_cfg,
                            session_repo=SessionRepository(),
                            event_repo=EventRepository(),
                            agent_run_service=AgentRunService(repo=AgentRunTaskRepository(), config=_cfg),
                            file_store=storage,
                            sandbox_repo=SandboxRepository(),
                        ).update_session_public_url(db, self._session_id, preview_url)
                    logger.info(f"Saved preview_url {preview_url} to session {self._session_id}")
                except Exception as e:
                    logger.warning(f"Failed to save preview_url to session: {e}")

        # Convert result to string if needed
        if isinstance(result, dict):
            result_str = json.dumps(result)
        elif isinstance(result, list):
            result_str = json.dumps(result)
        else:
            result_str = str(result) if result else ""

        # Create OpenAI format tool result (tool message)
        tool_message = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result_str,
        }

        self._tool_results.append(tool_message)
        self._openai_messages.append(tool_message)

        # Remove from pending if exists
        if tool_call_id and tool_call_id in self._pending_tool_calls:
            del self._pending_tool_calls[tool_call_id]

    async def _emit_to_socketio(self, event: RealtimeEvent) -> None:
        """Broadcast event to Socket.IO room for web clients visiting /:session_id.
        
        Uses Redis-backed session_manager for cross-pod communication in K8s deployments.
        Falls back to direct sio.emit() if session_manager is not available.
        """
        if not self._session_id:
            return

        try:
            event_type = event.type.value if hasattr(event.type, "value") else str(event.type)
            event_data = {
                "type": event_type,
                "content": event.content,
            }
            room = str(self._session_id)
            
            # Import here to avoid circular imports
            from ii_agent.core.redis import session_manager

            # Prefer Redis-backed session_manager for cross-pod support
            if session_manager is not None:
                await session_manager.emit(
                    "chat_event",
                    event_data,
                    room=room,
                    namespace="/",
                )
                logger.debug(f"Emitted event {event_type} to Socket.IO room {room} via Redis")
            elif self._sio:
                # Fallback to direct emit (single-pod only)
                await self._sio.emit("chat_event", event_data, room=room)
                logger.debug(f"Emitted event {event_type} to Socket.IO room {room} directly")
            else:
                logger.debug(f"No Socket.IO transport available for event {event_type}")
        except Exception as e:
            logger.warning(f"Failed to emit event to Socket.IO: {e}")

    async def _send_log_notification(self, level: str, logger_name: str, data: Dict[str, Any]) -> None:
        """Send a log notification via MCP server."""
        if not self._mcp_server:
            return

        try:
            # Create the logging notification
            notification = mcp_types.LoggingMessageNotification(
                method="notifications/message",
                params=mcp_types.LoggingMessageNotificationParams(
                    level=level,
                    logger=logger_name,
                    data=data,
                ),
            )
            # Send via the low-level MCP server
            # Note: This requires an active session context
            await self._mcp_server._mcp_server.send_notification(notification)
        except Exception as e:
            logger.debug(f"Failed to send log notification: {e}")

    async def send_sandbox_ready_notification(self, sandbox_url: str, session_id: str) -> None:
        """Send a notification that sandbox is ready with its URL.

        This is sent early in the agent execution so the widget can display
        the sandbox iframe as soon as it's available, rather than waiting
        for the entire tool execution to complete.
        """
        if not self._mcp_server:
            logger.debug("No MCP server available for sandbox ready notification")
            return

        try:
            event_data = {
                "type": "sandbox_ready",
                "sandbox_url": sandbox_url,
                "session_id": session_id,
                "status": "ready",
                "timestamp": time_module.time(),
            }
            await self._send_log_notification("info", "agent.sandbox_ready", event_data)
            logger.info(f"Sent sandbox_ready notification: {sandbox_url}")
        except Exception as e:
            logger.warning(f"Failed to send sandbox ready notification: {e}")

    async def _stream_event_to_client(self, event: RealtimeEvent) -> None:
        """Stream event to client via MCP logging notifications."""
        if not self._mcp_server:
            return

        try:
            event_type = event.type.value if hasattr(event.type, "value") else str(event.type)
            content = event.content

            # Build event data for notification
            event_data = {
                "type": event_type,
                "event_id": str(event.id) if event.id else None,
                "timestamp": event.timestamp,
                "event_count": self._event_count,
            }

            # Format content based on event type
            if event_type == "tool_call":
                tool_call_id = content.get("tool_call_id") or content.get("id") if isinstance(content, dict) else None
                tool_name = content.get("tool_name") or content.get("name") if isinstance(content, dict) else None
                tool_input = content.get("tool_input") or content.get("input") if isinstance(content, dict) else None
                event_data["tool_call"] = {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(tool_input) if isinstance(tool_input, dict) else str(tool_input or "{}"),
                    },
                }
                await self._send_log_notification("info", "agent.tool_call", event_data)

            elif event_type == "tool_result":
                tool_call_id = content.get("tool_call_id") or content.get("id") if isinstance(content, dict) else None
                tool_name = content.get("tool_name") or content.get("name") if isinstance(content, dict) else None
                result = (
                    content.get("result") or content.get("output") or content.get("content")
                    if isinstance(content, dict)
                    else None
                )
                # Truncate large results for logging
                result_preview = str(result)[:500] if result else ""
                event_data["tool_result"] = {
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                    "content": result_preview,
                }
                await self._send_log_notification("info", "agent.tool_result", event_data)

            elif event_type in ("agent_response", "agent_thinking"):
                text = content.get("text", "") if isinstance(content, dict) else str(content)
                if text:
                    # Use shorter preview for notification
                    text_preview = text[:500] + "..." if len(text) > 500 else text
                    event_data["message"] = {
                        "role": "assistant",
                        "content": text_preview,
                    }
                    await self._send_log_notification("info", f"agent.{event_type}", event_data)

            elif event_type == "error":
                error_msg = content.get("message") or content.get("error") if isinstance(content, dict) else str(content)
                event_data["error"] = {"message": error_msg}
                await self._send_log_notification("error", "agent.error", event_data)

            elif event_type in ("complete", "stream_complete"):
                event_data["status"] = "complete"
                await self._send_log_notification("info", "agent.complete", event_data)

            else:
                # For other event types, log with debug level
                content_str = json.dumps(content) if isinstance(content, dict) else str(content)
                content_preview = content_str[:300] if len(content_str) > 300 else content_str
                event_data["content"] = content_preview
                await self._send_log_notification("debug", f"agent.{event_type}", event_data)

        except anyio.ClosedResourceError:
            # Client disconnected - this is expected behavior, silently ignore
            pass
        except Exception as e:
            # Log other unexpected errors with full details
            logger.warning(f"[MCP] Failed to stream event to client: {type(e).__name__}: {e}", exc_info=True)

    def subscribe(self, subscriber) -> None:
        """No-op for interface compatibility."""
        pass

    def unsubscribe(self, subscriber) -> None:
        """No-op for interface compatibility."""
        pass

    def clear_subscribers(self) -> None:
        """No-op for interface compatibility."""
        pass

    def register_hook(self, hook) -> None:
        """Register an event hook."""
        self._hook_registry.register_hook(hook)

    def unregister_hook(self, hook) -> None:
        """Unregister an event hook."""
        self._hook_registry.unregister_hook(hook)

    def clear_hooks(self) -> None:
        """Remove all registered hooks."""
        self._hook_registry.clear_hooks()

    async def wait_for_completion(self) -> None:
        """Wait for the agent to complete by consuming events."""
        while not self._is_complete:
            try:
                await asyncio.wait_for(self._events.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

    def get_final_response(self) -> str:
        """Get the final response text."""
        return self._final_response or "Task completed."

    def get_tool_calls(self) -> list[Dict[str, Any]]:
        """Get all tool calls in OpenAI format."""
        return self._tool_calls

    def get_tool_results(self) -> list[Dict[str, Any]]:
        """Get all tool results in OpenAI format (tool messages)."""
        return self._tool_results

    def get_openai_messages(self) -> list[Dict[str, Any]]:
        """Get the complete conversation in OpenAI messages format.

        Returns the incrementally built list of messages including:
        - Assistant messages with tool_calls (added during TOOL_CALL events)
        - Tool messages with results (added during TOOL_RESULT events)
        - Final assistant message with text response (added at the end)
        """
        messages = list(self._openai_messages)  # Copy the incrementally built messages

        # Add final assistant response if available
        final_text = self.get_final_response()
        if final_text and final_text != "Task completed.":
            messages.append(
                {
                    "role": "assistant",
                    "content": final_text,
                }
            )
        elif not self._tool_calls:
            # Only add default message if there were no tool calls
            messages.append(
                {
                    "role": "assistant",
                    "content": final_text,
                }
            )

        return messages

    def get_openai_response(self) -> Dict[str, Any]:
        """Get the response in OpenAI Chat Completion format.

        Returns a dict similar to OpenAI's chat.completions response.
        """
        messages = self.get_openai_messages()

        # Get the last assistant message for the response
        last_assistant_msg = None
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                last_assistant_msg = msg
                break

        if last_assistant_msg is None:
            last_assistant_msg = {"role": "assistant", "content": "Task completed."}

        # Build OpenAI-style response
        response = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time_module.time()),
            "model": "ii-agent",
            "choices": [
                {
                    "index": 0,
                    "message": last_assistant_msg,
                    "finish_reason": "tool_calls" if last_assistant_msg.get("tool_calls") else "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }

        return response
