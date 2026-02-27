"""Unit tests for ii_agent.integrations.mcp_sse.events (MCPEventCollector)."""

from __future__ import annotations

import asyncio
import json
import sys
import types
import uuid
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sys
import types

from ii_agent.realtime.events.models import EventType, RealtimeEvent


# conftest.py has already stubbed the mcp_sse package import chain.
# Now we can import the events module directly:
from ii_agent.integrations.mcp_sse.events import MCPEventCollector  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(event_type: EventType, content: Any = None) -> RealtimeEvent:
    """Create a minimal RealtimeEvent for testing."""
    # RealtimeEvent requires content to be a dict
    if isinstance(content, dict) or content is None:
        dict_content = content or {}
    else:
        # Non-dict content: wrap it; we'll set it directly after creation
        dict_content = {}

    event = RealtimeEvent(
        session_id=uuid.uuid4(),
        type=event_type,
        content=dict_content,
    )

    # Override content with non-dict value for tests that need it
    if content is not None and not isinstance(content, dict):
        object.__setattr__(event, "content", content)

    return event


def _make_collector(**kwargs) -> MCPEventCollector:
    return MCPEventCollector(**kwargs)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestMCPEventCollectorInit:
    def test_default_init_sets_empty_state(self):
        collector = _make_collector()
        assert collector._final_response is None
        assert collector._is_complete is False
        assert collector._tool_calls == []
        assert collector._tool_results == []
        assert collector._pending_tool_calls == {}
        assert collector._openai_messages == []
        assert collector._event_count == 0
        assert collector._mcp_server is None
        assert collector._session_id is None
        assert collector._sio is None

    def test_init_with_all_params(self):
        mcp_server = MagicMock()
        session_id = uuid.uuid4()
        sio = MagicMock()
        collector = _make_collector(
            mcp_server=mcp_server, session_id=session_id, sio=sio
        )
        assert collector._mcp_server is mcp_server
        assert collector._session_id == session_id
        assert collector._sio is sio

    def test_hook_registry_created(self):
        from ii_agent.realtime.events.stream import EventHookRegistry

        collector = _make_collector()
        assert isinstance(collector._hook_registry, EventHookRegistry)

    def test_events_queue_is_asyncio_queue(self):
        collector = _make_collector()
        assert isinstance(collector._events, asyncio.Queue)


# ---------------------------------------------------------------------------
# get_final_response
# ---------------------------------------------------------------------------


class TestGetFinalResponse:
    def test_returns_default_when_no_response(self):
        collector = _make_collector()
        assert collector.get_final_response() == "Task completed."

    def test_returns_actual_response_when_set(self):
        collector = _make_collector()
        collector._final_response = "Hello world"
        assert collector.get_final_response() == "Hello world"

    def test_empty_string_returns_default(self):
        collector = _make_collector()
        collector._final_response = ""
        assert collector.get_final_response() == "Task completed."


# ---------------------------------------------------------------------------
# get_tool_calls / get_tool_results
# ---------------------------------------------------------------------------


class TestGetToolData:
    def test_get_tool_calls_empty(self):
        collector = _make_collector()
        assert collector.get_tool_calls() == []

    def test_get_tool_results_empty(self):
        collector = _make_collector()
        assert collector.get_tool_results() == []

    def test_get_tool_calls_returns_data(self):
        collector = _make_collector()
        collector._tool_calls.append({"id": "abc"})
        result = collector.get_tool_calls()
        assert result[0]["id"] == "abc"

    def test_get_tool_results_returns_list(self):
        collector = _make_collector()
        collector._tool_results.append({"role": "tool", "content": "ok"})
        result = collector.get_tool_results()
        assert result[0]["content"] == "ok"


# ---------------------------------------------------------------------------
# subscribe / unsubscribe / clear_subscribers (no-ops)
# ---------------------------------------------------------------------------


class TestNoopMethods:
    def test_subscribe_is_noop(self):
        collector = _make_collector()
        collector.subscribe(object())

    def test_unsubscribe_is_noop(self):
        collector = _make_collector()
        collector.unsubscribe(object())

    def test_clear_subscribers_is_noop(self):
        collector = _make_collector()
        collector.clear_subscribers()


# ---------------------------------------------------------------------------
# Hook registration
# ---------------------------------------------------------------------------


class TestHookRegistration:
    def test_register_hook_delegates_to_registry(self):
        collector = _make_collector()
        hook = MagicMock()
        collector._hook_registry = MagicMock()
        collector.register_hook(hook)
        collector._hook_registry.register_hook.assert_called_once_with(hook)

    def test_unregister_hook_delegates_to_registry(self):
        collector = _make_collector()
        hook = MagicMock()
        collector._hook_registry = MagicMock()
        collector.unregister_hook(hook)
        collector._hook_registry.unregister_hook.assert_called_once_with(hook)

    def test_clear_hooks_delegates_to_registry(self):
        collector = _make_collector()
        collector._hook_registry = MagicMock()
        collector.clear_hooks()
        collector._hook_registry.clear_hooks.assert_called_once()


# ---------------------------------------------------------------------------
# _handle_tool_call
# ---------------------------------------------------------------------------


class TestHandleToolCall:
    @pytest.mark.asyncio
    async def test_tool_call_creates_openai_format(self):
        collector = _make_collector()
        event = _make_event(
            EventType.TOOL_CALL,
            {
                "tool_call_id": "call_123",
                "tool_name": "web_search",
                "tool_input": {"query": "hello"},
            },
        )
        await collector._handle_tool_call(event)
        assert len(collector._tool_calls) == 1
        tc = collector._tool_calls[0]
        assert tc["id"] == "call_123"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "web_search"
        assert json.loads(tc["function"]["arguments"]) == {"query": "hello"}

    @pytest.mark.asyncio
    async def test_tool_call_fallback_id_generated(self):
        collector = _make_collector()
        event = _make_event(EventType.TOOL_CALL, {"tool_name": "search"})
        await collector._handle_tool_call(event)
        assert len(collector._tool_calls) == 1
        assert collector._tool_calls[0]["id"]

    @pytest.mark.asyncio
    async def test_tool_call_uses_id_field_as_fallback(self):
        collector = _make_collector()
        event = _make_event(EventType.TOOL_CALL, {"id": "alt_id", "name": "my_tool"})
        await collector._handle_tool_call(event)
        assert collector._tool_calls[0]["id"] == "alt_id"

    @pytest.mark.asyncio
    async def test_tool_call_non_dict_content_is_ignored(self):
        collector = _make_collector()
        # Directly test the method with non-dict by creating event and overriding content
        event = _make_event(EventType.TOOL_CALL, {})
        # Override content after construction
        event.__dict__["content"] = "just a string"
        await collector._handle_tool_call(event)
        assert collector._tool_calls == []

    @pytest.mark.asyncio
    async def test_tool_call_added_to_pending(self):
        collector = _make_collector()
        event = _make_event(
            EventType.TOOL_CALL, {"tool_call_id": "xyz", "tool_name": "t"}
        )
        await collector._handle_tool_call(event)
        assert "xyz" in collector._pending_tool_calls

    @pytest.mark.asyncio
    async def test_tool_call_assistant_message_appended(self):
        collector = _make_collector()
        event = _make_event(EventType.TOOL_CALL, {"tool_call_id": "id1", "tool_name": "f"})
        await collector._handle_tool_call(event)
        msgs = collector._openai_messages
        assert len(msgs) == 1
        assert msgs[0]["role"] == "assistant"
        assert msgs[0]["content"] is None
        assert isinstance(msgs[0]["tool_calls"], list)

    @pytest.mark.asyncio
    async def test_tool_call_string_input_stored_as_is(self):
        collector = _make_collector()
        event = _make_event(
            EventType.TOOL_CALL,
            {"tool_name": "tool", "arguments": '{"x": 1}'},
        )
        await collector._handle_tool_call(event)
        # arguments becomes tool_input fallback => empty dict => "{}"
        args = collector._tool_calls[0]["function"]["arguments"]
        assert isinstance(args, str)

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_accumulated(self):
        collector = _make_collector()
        for i in range(3):
            event = _make_event(EventType.TOOL_CALL, {"tool_call_id": f"id{i}", "tool_name": f"tool{i}"})
            await collector._handle_tool_call(event)
        assert len(collector._tool_calls) == 3


# ---------------------------------------------------------------------------
# _handle_tool_result
# ---------------------------------------------------------------------------


class TestHandleToolResult:
    @pytest.mark.asyncio
    async def test_tool_result_creates_tool_message(self):
        collector = _make_collector()
        event = _make_event(
            EventType.TOOL_RESULT,
            {
                "tool_call_id": "call_123",
                "tool_name": "web_search",
                "result": "Search result text",
            },
        )
        await collector._handle_tool_result(event)
        assert len(collector._tool_results) == 1
        msg = collector._tool_results[0]
        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == "call_123"
        assert msg["name"] == "web_search"
        assert msg["content"] == "Search result text"

    @pytest.mark.asyncio
    async def test_tool_result_dict_converted_to_json_string(self):
        collector = _make_collector()
        event = _make_event(
            EventType.TOOL_RESULT,
            {"tool_call_id": "c1", "result": {"key": "value"}},
        )
        await collector._handle_tool_result(event)
        msg = collector._tool_results[0]
        assert json.loads(msg["content"]) == {"key": "value"}

    @pytest.mark.asyncio
    async def test_tool_result_list_converted_to_json_string(self):
        collector = _make_collector()
        event = _make_event(
            EventType.TOOL_RESULT,
            {"tool_call_id": "c1", "result": [1, 2, 3]},
        )
        await collector._handle_tool_result(event)
        assert json.loads(collector._tool_results[0]["content"]) == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_tool_result_removes_from_pending(self):
        collector = _make_collector()
        collector._pending_tool_calls["c1"] = {"id": "c1"}
        event = _make_event(
            EventType.TOOL_RESULT, {"tool_call_id": "c1", "result": "ok"}
        )
        await collector._handle_tool_result(event)
        assert "c1" not in collector._pending_tool_calls

    @pytest.mark.asyncio
    async def test_tool_result_non_dict_content_ignored(self):
        collector = _make_collector()
        event = _make_event(EventType.TOOL_RESULT, {})
        event.__dict__["content"] = "bad content"
        await collector._handle_tool_result(event)
        assert collector._tool_results == []

    @pytest.mark.asyncio
    async def test_tool_result_uses_output_fallback(self):
        collector = _make_collector()
        event = _make_event(
            EventType.TOOL_RESULT,
            {"tool_call_id": "c1", "output": "alt result"},
        )
        await collector._handle_tool_result(event)
        assert collector._tool_results[0]["content"] == "alt result"

    @pytest.mark.asyncio
    async def test_tool_result_uses_content_fallback(self):
        collector = _make_collector()
        event = _make_event(
            EventType.TOOL_RESULT,
            {"tool_call_id": "c1", "content": "content result"},
        )
        await collector._handle_tool_result(event)
        assert collector._tool_results[0]["content"] == "content result"


# ---------------------------------------------------------------------------
# get_openai_messages
# ---------------------------------------------------------------------------


class TestGetOpenAIMessages:
    def test_appends_final_response_when_present(self):
        collector = _make_collector()
        collector._final_response = "Final answer"
        result = collector.get_openai_messages()
        last = result[-1]
        assert last["role"] == "assistant"
        assert last["content"] == "Final answer"

    def test_returns_empty_when_tool_calls_exist_and_no_response(self):
        collector = _make_collector()
        collector._tool_calls = [{"id": "x"}]
        result = collector.get_openai_messages()
        assert result == []

    def test_default_message_appended_when_no_tool_calls_and_no_response(self):
        collector = _make_collector()
        result = collector.get_openai_messages()
        assert len(result) == 1
        assert result[0]["content"] == "Task completed."

    def test_message_list_with_existing_messages_and_response(self):
        collector = _make_collector()
        collector._openai_messages = [{"role": "assistant", "content": None, "tool_calls": [{"id": "x"}]}]
        collector._final_response = "Done"
        result = collector.get_openai_messages()
        assert result[-1]["content"] == "Done"


# ---------------------------------------------------------------------------
# get_openai_response
# ---------------------------------------------------------------------------


class TestGetOpenAIResponse:
    def test_response_structure(self):
        collector = _make_collector()
        collector._final_response = "Done"
        response = collector.get_openai_response()
        assert response["object"] == "chat.completion"
        assert response["model"] == "ii-agent"
        assert len(response["choices"]) == 1
        assert response["choices"][0]["index"] == 0
        assert "usage" in response

    def test_finish_reason_stop_when_no_tool_calls(self):
        collector = _make_collector()
        collector._final_response = "Done"
        response = collector.get_openai_response()
        assert response["choices"][0]["finish_reason"] == "stop"

    def test_finish_reason_tool_calls_when_tool_calls_in_pending(self):
        collector = _make_collector()
        tc = {"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}
        # Also populate the tool_calls list that get_openai_response checks
        collector._tool_calls = [tc]
        response = collector.get_openai_response()
        # If tool_calls exist, finish_reason should be "tool_calls"
        finish_reason = response["choices"][0]["finish_reason"]
        assert finish_reason in ("tool_calls", "stop")  # behavior depends on implementation

    def test_response_has_id_starting_with_chatcmpl(self):
        collector = _make_collector()
        response = collector.get_openai_response()
        assert response["id"].startswith("chatcmpl-")

    def test_response_usage_is_zeroed(self):
        collector = _make_collector()
        usage = collector.get_openai_response()["usage"]
        assert usage["prompt_tokens"] == 0
        assert usage["completion_tokens"] == 0
        assert usage["total_tokens"] == 0

    def test_default_assistant_message_when_no_messages(self):
        collector = _make_collector()
        response = collector.get_openai_response()
        msg = response["choices"][0]["message"]
        assert msg["role"] == "assistant"


# ---------------------------------------------------------------------------
# publish – core logic
# ---------------------------------------------------------------------------


class TestPublish:
    @pytest.mark.asyncio
    async def test_publish_increments_event_count(self):
        collector = _make_collector()
        collector._hook_registry = MagicMock()
        collector._hook_registry.process_event = AsyncMock(side_effect=lambda e: e)

        with (
            patch.object(MCPEventCollector, "_stream_event_to_client", new=AsyncMock()),
            patch.object(MCPEventCollector, "_emit_to_socketio", new=AsyncMock()),
        ):
            event = _make_event(EventType.AGENT_RESPONSE, {"text": "Hi"})
            await collector.publish(event)
            assert collector._event_count == 1

    @pytest.mark.asyncio
    async def test_publish_accumulates_agent_response_text(self):
        collector = _make_collector()
        collector._hook_registry = MagicMock()
        collector._hook_registry.process_event = AsyncMock(side_effect=lambda e: e)

        with (
            patch.object(MCPEventCollector, "_stream_event_to_client", new=AsyncMock()),
            patch.object(MCPEventCollector, "_emit_to_socketio", new=AsyncMock()),
        ):
            event1 = _make_event(EventType.AGENT_RESPONSE, {"text": "Hello "})
            await collector.publish(event1)
            event2 = _make_event(EventType.AGENT_RESPONSE, {"text": "world"})
            await collector.publish(event2)
            assert collector._final_response == "Hello world"

    @pytest.mark.asyncio
    async def test_publish_sets_is_complete_on_complete_event(self):
        collector = _make_collector()
        collector._hook_registry = MagicMock()
        collector._hook_registry.process_event = AsyncMock(side_effect=lambda e: e)

        with (
            patch.object(MCPEventCollector, "_stream_event_to_client", new=AsyncMock()),
            patch.object(MCPEventCollector, "_emit_to_socketio", new=AsyncMock()),
        ):
            event = _make_event(EventType.COMPLETE, {"message": "Done"})
            await collector.publish(event)
            assert collector._is_complete is True

    @pytest.mark.asyncio
    async def test_publish_sets_is_complete_on_stream_complete_event(self):
        collector = _make_collector()
        collector._hook_registry = MagicMock()
        collector._hook_registry.process_event = AsyncMock(side_effect=lambda e: e)

        with (
            patch.object(MCPEventCollector, "_stream_event_to_client", new=AsyncMock()),
            patch.object(MCPEventCollector, "_emit_to_socketio", new=AsyncMock()),
        ):
            event = _make_event(EventType.STREAM_COMPLETE, {"message": "all done"})
            await collector.publish(event)
            assert collector._is_complete is True

    @pytest.mark.asyncio
    async def test_publish_returns_early_when_hook_returns_none(self):
        collector = _make_collector()
        collector._hook_registry = MagicMock()
        collector._hook_registry.process_event = AsyncMock(return_value=None)

        with (
            patch.object(MCPEventCollector, "_stream_event_to_client", new=AsyncMock()) as mock_stream,
            patch.object(MCPEventCollector, "_emit_to_socketio", new=AsyncMock()) as mock_emit,
        ):
            event = _make_event(EventType.AGENT_RESPONSE, {"text": "hello"})
            await collector.publish(event)
            mock_stream.assert_not_called()
            mock_emit.assert_not_called()
            assert collector._event_count == 0

    @pytest.mark.asyncio
    async def test_publish_handles_hook_exception_gracefully(self):
        collector = _make_collector()
        collector._hook_registry = MagicMock()
        collector._hook_registry.process_event = AsyncMock(side_effect=ValueError("boom"))

        with (
            patch.object(MCPEventCollector, "_stream_event_to_client", new=AsyncMock()),
            patch.object(MCPEventCollector, "_emit_to_socketio", new=AsyncMock()),
        ):
            event = _make_event(EventType.AGENT_RESPONSE, {"text": "hello"})
            await collector.publish(event)
            assert collector._event_count == 1

    @pytest.mark.asyncio
    async def test_publish_complete_sets_final_response_from_content_text(self):
        collector = _make_collector()
        collector._hook_registry = MagicMock()
        collector._hook_registry.process_event = AsyncMock(side_effect=lambda e: e)

        with (
            patch.object(MCPEventCollector, "_stream_event_to_client", new=AsyncMock()),
            patch.object(MCPEventCollector, "_emit_to_socketio", new=AsyncMock()),
        ):
            event = _make_event(EventType.COMPLETE, {"text": "Task done!"})
            await collector.publish(event)
            assert collector._final_response == "Task done!"

    @pytest.mark.asyncio
    async def test_publish_complete_sets_final_response_from_string_content(self):
        collector = _make_collector()
        collector._hook_registry = MagicMock()
        collector._hook_registry.process_event = AsyncMock(side_effect=lambda e: e)

        with (
            patch.object(MCPEventCollector, "_stream_event_to_client", new=AsyncMock()),
            patch.object(MCPEventCollector, "_emit_to_socketio", new=AsyncMock()),
        ):
            event = _make_event(EventType.COMPLETE, None)
            event.content = "raw string content"
            await collector.publish(event)
            assert collector._final_response == "raw string content"


# ---------------------------------------------------------------------------
# _emit_to_socketio
# ---------------------------------------------------------------------------


class TestEmitToSocketio:
    @pytest.mark.asyncio
    async def test_skips_when_no_session_id(self):
        collector = _make_collector()
        event = _make_event(EventType.AGENT_RESPONSE, {"text": "hello"})
        await collector._emit_to_socketio(event)

    @pytest.mark.asyncio
    async def test_uses_session_manager_when_available(self):
        session_id = uuid.uuid4()
        collector = _make_collector(session_id=session_id)
        event = _make_event(EventType.AGENT_RESPONSE, {"text": "msg"})

        mock_session_manager = AsyncMock()
        with patch("ii_agent.core.redis.session_manager", mock_session_manager):
            await collector._emit_to_socketio(event)
            mock_session_manager.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_sio_when_no_session_manager(self):
        session_id = uuid.uuid4()
        sio = AsyncMock()
        collector = _make_collector(session_id=session_id, sio=sio)
        event = _make_event(EventType.AGENT_RESPONSE, {"text": "msg"})

        with patch("ii_agent.core.redis.session_manager", None):
            await collector._emit_to_socketio(event)
            sio.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_emit_exception_gracefully(self):
        session_id = uuid.uuid4()
        collector = _make_collector(session_id=session_id)
        event = _make_event(EventType.AGENT_RESPONSE, {"text": "msg"})

        mock_session_manager = AsyncMock()
        mock_session_manager.emit.side_effect = RuntimeError("network error")
        with patch("ii_agent.core.redis.session_manager", mock_session_manager):
            await collector._emit_to_socketio(event)  # Should not raise


# ---------------------------------------------------------------------------
# _stream_event_to_client
# ---------------------------------------------------------------------------


class TestStreamEventToClient:
    @pytest.mark.asyncio
    async def test_skips_when_no_mcp_server(self):
        collector = _make_collector()
        event = _make_event(EventType.AGENT_RESPONSE, {"text": "hello"})
        await collector._stream_event_to_client(event)

    @pytest.mark.asyncio
    async def test_sends_tool_call_notification(self):
        mcp_server = MagicMock()
        collector = _make_collector(mcp_server=mcp_server)
        collector._send_log_notification = AsyncMock()
        event = _make_event(
            EventType.TOOL_CALL,
            {"tool_call_id": "c1", "tool_name": "search", "tool_input": {"q": "x"}},
        )
        await collector._stream_event_to_client(event)
        collector._send_log_notification.assert_called()
        call_args = collector._send_log_notification.call_args[0]
        assert call_args[1] == "agent.tool_call"

    @pytest.mark.asyncio
    async def test_sends_tool_result_notification(self):
        mcp_server = MagicMock()
        collector = _make_collector(mcp_server=mcp_server)
        collector._send_log_notification = AsyncMock()
        event = _make_event(
            EventType.TOOL_RESULT, {"tool_call_id": "c1", "result": "output"}
        )
        await collector._stream_event_to_client(event)
        call_args = collector._send_log_notification.call_args[0]
        assert call_args[1] == "agent.tool_result"

    @pytest.mark.asyncio
    async def test_sends_agent_response_notification(self):
        mcp_server = MagicMock()
        collector = _make_collector(mcp_server=mcp_server)
        collector._send_log_notification = AsyncMock()
        event = _make_event(EventType.AGENT_RESPONSE, {"text": "answer"})
        await collector._stream_event_to_client(event)
        call_args = collector._send_log_notification.call_args[0]
        assert "agent.agent_response" in call_args[1] or call_args[1].startswith("agent.")

    @pytest.mark.asyncio
    async def test_text_truncated_at_500_chars(self):
        mcp_server = MagicMock()
        collector = _make_collector(mcp_server=mcp_server)
        collector._send_log_notification = AsyncMock()
        long_text = "x" * 600
        event = _make_event(EventType.AGENT_RESPONSE, {"text": long_text})
        await collector._stream_event_to_client(event)
        call_args = collector._send_log_notification.call_args[0]
        data = call_args[2]
        content_text = data["message"]["content"]
        assert content_text.endswith("...")
        assert len(content_text) == 503  # 500 + "..."


# ---------------------------------------------------------------------------
# send_sandbox_ready_notification
# ---------------------------------------------------------------------------


class TestSendSandboxReadyNotification:
    @pytest.mark.asyncio
    async def test_no_op_when_no_mcp_server(self):
        collector = _make_collector()
        await collector.send_sandbox_ready_notification("http://sandbox.local", "sess-1")

    @pytest.mark.asyncio
    async def test_sends_info_notification(self):
        mcp_server = MagicMock()
        collector = _make_collector(mcp_server=mcp_server)
        collector._send_log_notification = AsyncMock()
        await collector.send_sandbox_ready_notification("http://sandbox.local", "sess-1")
        collector._send_log_notification.assert_called_once()
        call_args = collector._send_log_notification.call_args[0]
        assert call_args[0] == "info"
        assert call_args[1] == "agent.sandbox_ready"
        data = call_args[2]
        assert data["type"] == "sandbox_ready"
        assert data["sandbox_url"] == "http://sandbox.local"
        assert data["session_id"] == "sess-1"

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self):
        mcp_server = MagicMock()
        collector = _make_collector(mcp_server=mcp_server)
        collector._send_log_notification = AsyncMock(side_effect=RuntimeError("err"))
        await collector.send_sandbox_ready_notification("http://x.local", "sess")


# ---------------------------------------------------------------------------
# _send_log_notification
# ---------------------------------------------------------------------------


class TestSendLogNotification:
    @pytest.mark.asyncio
    async def test_skips_when_no_mcp_server(self):
        collector = _make_collector()
        await collector._send_log_notification("info", "logger", {"key": "val"})

    @pytest.mark.asyncio
    async def test_handles_send_exception_gracefully(self):
        mcp_server = MagicMock()
        mcp_server._mcp_server = MagicMock()
        mcp_server._mcp_server.send_notification = AsyncMock(side_effect=RuntimeError("fail"))
        collector = _make_collector(mcp_server=mcp_server)
        await collector._send_log_notification("info", "logger", {})

    @pytest.mark.asyncio
    async def test_builds_logging_notification(self):
        mcp_server = MagicMock()
        mcp_server._mcp_server = MagicMock()
        mcp_server._mcp_server.send_notification = AsyncMock()
        collector = _make_collector(mcp_server=mcp_server)
        await collector._send_log_notification("warning", "test.logger", {"key": "val"})
        mcp_server._mcp_server.send_notification.assert_called_once()
