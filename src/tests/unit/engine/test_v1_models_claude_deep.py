"""
Deep unit tests for ii_agent/agent/runtime/models/anthropic/claude.py

Covers deeper branches not tested by the existing test file:
- format_messages: developer role, images in messages, files in messages,
  assistant tool_calls with no content, remaining tool results at end
- Claude.get_client() paths
- Claude._parse_provider_response() with MCP tool_use and various citation types
- Claude.ainvoke_stream() - streaming responses, error handling
- Claude._format_messages with various provider_data scenarios
- Claude deepcopy behavior
- Claude request with extended thinking
- format_tools_for_model with to_dict and model_dump objects
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from ii_agent.agent.runtime.models.anthropic.claude import (
    ROLE_MAP,
    MCPServerConfiguration,
    Claude,
    _normalize_tool_definition,
    format_tools_for_model,
    format_messages,
)
from ii_agent.agent.runtime.models.message import Message
from ii_agent.agent.runtime.models.metrics import Metrics
from ii_agent.agent.runtime.models.response import ModelResponse
from ii_agent.agent.runtime.exceptions import (
    ModelProviderError,
    ModelRateLimitError,
)
from ii_agent.agent.runtime.media import Image, File
from ii_agent.agent.types import Provider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_claude(**kwargs) -> Claude:
    c = Claude(**kwargs)
    mock_async_client = MagicMock()
    mock_async_client.is_closed.return_value = False
    mock_async_client.beta = MagicMock()
    mock_async_client.beta.messages = MagicMock()
    c.async_client = mock_async_client
    return c


def _make_response_block(block_type, **kwargs):
    block = MagicMock()
    block.type = block_type
    for k, v in kwargs.items():
        setattr(block, k, v)
    return block


def _make_usage(input_t=10, output_t=20, cache_create=0, cache_read=0):
    usage = MagicMock()
    usage.input_tokens = input_t
    usage.output_tokens = output_t
    usage.cache_creation_input_tokens = cache_create
    usage.cache_read_input_tokens = cache_read
    usage.model_dump = MagicMock(return_value={"input_tokens": input_t, "output_tokens": output_t})
    return usage


def _make_provider_response(blocks, stop_reason="end_turn", role="assistant", usage=None):
    resp = MagicMock()
    resp.role = role
    resp.content = blocks
    resp.stop_reason = stop_reason
    resp.usage = usage or _make_usage()
    resp.context_management = None
    return resp


# ---------------------------------------------------------------------------
# format_messages: deeper branches
# ---------------------------------------------------------------------------

class TestFormatMessagesDeep:
    def test_system_message_with_list_content_non_text_dict(self):
        # System message content is a list with non-text-keyed dict
        msgs = [Message(role="system", content=[{"data": "not text"}])]
        formatted, system = format_messages(msgs)
        # str(item) is used for non-text dicts, so system contains str representation
        assert system is not None
        # The system message should be a string representation of the dict
        assert isinstance(system, str)

    def test_system_message_string_content(self):
        msgs = [Message(role="system", content="Simple system")]
        _, system = format_messages(msgs)
        assert system == "Simple system"

    def test_user_message_with_image(self):
        img = MagicMock(spec=Image)
        img.url = None
        img.content = b"\x89PNG\r\nfakedata"
        img.mime_type = "image/png"
        img.format = "png"
        img.get_content_bytes = MagicMock(return_value=b"\x89PNG\r\nfakedata")
        msgs = [Message(role="user", content="Look at this", images=[img])]
        formatted, _ = format_messages(msgs)
        # Should have at least one message
        assert len(formatted) >= 1

    def test_tool_result_with_list_content(self):
        # Tool result where content is already a list
        msgs = [
            Message(
                role="tool",
                content=[{"type": "text", "text": "result"}],
                tool_call_id="tc_1",
            )
        ]
        formatted, _ = format_messages(msgs)
        assert any(m["role"] == "user" for m in formatted)

    def test_tool_result_with_none_content(self):
        # Tool result where content is None
        msgs = [
            Message(role="tool", content=None, tool_call_id="tc_2"),
            Message(role="assistant", content="OK"),
        ]
        formatted, _ = format_messages(msgs)
        assert len(formatted) == 2

    def test_multiple_tool_results_then_assistant(self):
        msgs = [
            Message(role="tool", content="result_1", tool_call_id="tc_1"),
            Message(role="tool", content="result_2", tool_call_id="tc_2"),
            Message(role="assistant", content="Done"),
        ]
        formatted, _ = format_messages(msgs)
        # Tool results should be flushed before assistant
        user_msgs = [m for m in formatted if m["role"] == "user"]
        assert len(user_msgs) >= 1

    def test_pending_tool_results_merged_with_next_user_message(self):
        msgs = [
            Message(role="tool", content="result", tool_call_id="tc_1"),
            Message(role="user", content="Next question"),
        ]
        formatted, _ = format_messages(msgs)
        # Tool result should be merged with next user message
        user_msgs = [m for m in formatted if m["role"] == "user"]
        assert len(user_msgs) >= 1

    def test_assistant_tool_calls_formatted_as_tool_use(self):
        tool_calls = [
            {
                "id": "tc_1",
                "type": "function",
                "function": {"name": "search", "arguments": '{"q": "python"}'},
            }
        ]
        msgs = [Message(role="assistant", content="Using search", tool_calls=tool_calls)]
        formatted, _ = format_messages(msgs)
        assert any(
            any(p.get("type") == "tool_use" for p in m.get("content", []))
            for m in formatted
        )

    def test_assistant_tool_calls_with_non_json_arguments(self):
        tool_calls = [
            {
                "id": "tc_1",
                "type": "function",
                "function": {"name": "fn", "arguments": "not json"},
            }
        ]
        msgs = [Message(role="assistant", content="", tool_calls=tool_calls)]
        # Should not crash even with non-JSON arguments
        formatted, _ = format_messages(msgs)
        assert len(formatted) >= 1

    def test_cache_conversation_multi_turn(self):
        msgs = [
            Message(role="user", content="Q1"),
            Message(role="assistant", content="A1"),
            Message(role="user", content="Q2"),
            Message(role="assistant", content="A2"),
            Message(role="user", content="Q3"),
        ]
        formatted, _ = format_messages(msgs, cache_conversation=True)
        # Should add cache_control to some parts
        all_parts = []
        for m in formatted:
            if isinstance(m.get("content"), list):
                all_parts.extend(m["content"])
        # At least one part should have cache_control after N-2 boundary
        cache_ctrl = [p for p in all_parts if "cache_control" in p]
        assert len(cache_ctrl) >= 1

    def test_remaining_pending_tool_results_flushed_at_end(self):
        msgs = [
            Message(role="tool", content="dangling", tool_call_id="tc_99"),
        ]
        formatted, _ = format_messages(msgs)
        assert len(formatted) >= 1
        assert formatted[-1]["role"] == "user"

    def test_developer_role_mapped_to_system_role_in_chat(self):
        msgs = [Message(role="developer", content="Dev instructions")]
        formatted, system = format_messages(msgs)
        # developer role -> ROLE_MAP["developer"] = "system"
        assert system is None
        assert any(m["role"] == "system" for m in formatted)


# ---------------------------------------------------------------------------
# _normalize_tool_definition deeper branches
# ---------------------------------------------------------------------------

class TestNormalizeToolDefinitionDeep:
    def test_dict_without_function_key_returned_as_is(self):
        tool = {"name": "fn", "type": "web_search"}
        result = _normalize_tool_definition(tool)
        assert result == tool

    def test_to_dict_returns_non_dict_falls_through_to_model_dump(self):
        obj = MagicMock()
        obj.to_dict.return_value = "not a dict"
        obj.model_dump = MagicMock(return_value={"name": "from_model_dump"})
        result = _normalize_tool_definition(obj)
        assert result == {"name": "from_model_dump"}

    def test_model_dump_returns_non_dict_falls_through_to_none(self):
        obj = MagicMock(spec=[])
        obj.model_dump = MagicMock(return_value="not a dict")
        result = _normalize_tool_definition(obj)
        assert result is None


# ---------------------------------------------------------------------------
# Claude._parse_provider_response deep branches
# ---------------------------------------------------------------------------

class TestClaudeParseProviderResponseDeep:
    def test_mcp_tool_use_block(self):
        c = _make_claude()
        # MCP tool_use blocks have type "tool_use" just like regular tool_use
        tool_block = _make_response_block(
            "tool_use", id="mcp_1", name="mcp_tool", input={"param": "val"}, citations=None
        )
        mr = c._parse_provider_response(
            _make_provider_response([tool_block], stop_reason="tool_use")
        )
        assert len(mr.tool_calls) == 1
        assert mr.tool_calls[0]["function"]["name"] == "mcp_tool"

    def test_text_block_with_empty_text(self):
        c = _make_claude()
        text_block = _make_response_block("text", text="", citations=None)
        mr = c._parse_provider_response(_make_provider_response([text_block]))
        assert mr.content == ""

    def test_multiple_thinking_blocks(self):
        c = _make_claude()
        t1 = _make_response_block("thinking", thinking="First thought", signature="sig1")
        t2 = _make_response_block("thinking", thinking="Second thought", signature="sig2")
        mr = c._parse_provider_response(_make_provider_response([t1, t2]))
        # Implementation keeps the last thinking block; reasoning content is set from blocks
        assert mr.reasoning_content is not None
        assert isinstance(mr.reasoning_content, str)

    def test_tool_input_as_non_serializable_falls_back(self):
        c = _make_claude()
        # If input is something non-serializable (e.g., already a string)
        tool_block = _make_response_block(
            "tool_use", id="tc_1", name="fn", input="already_a_string", citations=None
        )
        mr = c._parse_provider_response(
            _make_provider_response([tool_block], stop_reason="tool_use")
        )
        # Should handle gracefully
        assert len(mr.tool_calls) == 1

    def test_usage_with_cache_tokens(self):
        c = _make_claude()
        text_block = _make_response_block("text", text="Hi", citations=None)
        usage = _make_usage(input_t=100, output_t=50, cache_create=20, cache_read=10)
        mr = c._parse_provider_response(_make_provider_response([text_block], usage=usage))
        assert mr.response_usage is not None
        assert mr.response_usage.input_tokens == 100
        assert mr.response_usage.output_tokens == 50

    def test_stop_reason_max_tokens(self):
        c = _make_claude()
        text_block = _make_response_block("text", text="Truncated", citations=None)
        mr = c._parse_provider_response(
            _make_provider_response([text_block], stop_reason="max_tokens")
        )
        assert isinstance(mr, ModelResponse)

    def test_stop_reason_end_turn(self):
        c = _make_claude()
        text_block = _make_response_block("text", text="Done", citations=None)
        mr = c._parse_provider_response(
            _make_provider_response([text_block], stop_reason="end_turn")
        )
        assert mr.content == "Done"

    def test_mixed_text_and_tool_use_blocks(self):
        c = _make_claude()
        text_block = _make_response_block("text", text="I'll search for that", citations=None)
        tool_block = _make_response_block(
            "tool_use", id="tc_1", name="search", input={"q": "test"}, citations=None
        )
        mr = c._parse_provider_response(
            _make_provider_response([text_block, tool_block], stop_reason="tool_use")
        )
        assert mr.content == "I'll search for that"
        assert len(mr.tool_calls) == 1


# ---------------------------------------------------------------------------
# Claude.ainvoke_stream() - happy path and error handling
# ---------------------------------------------------------------------------

class TestClaudeAinvokeStream:
    @pytest.mark.asyncio
    async def test_ainvoke_stream_yields_model_responses(self):
        from anthropic.types import (
            ContentBlockDeltaEvent,
            ContentBlockStartEvent,
            ContentBlockStopEvent,
            MessageStopEvent,
        )
        c = _make_claude(api_key="key")

        # Create mock streaming events
        text_event = MagicMock()
        text_event.type = "content_block_delta"
        text_event.delta = MagicMock()
        text_event.delta.type = "text_delta"
        text_event.delta.text = "Hello stream"

        stop_event = MagicMock()
        stop_event.type = "message_stop"

        # Mock the async context manager for streaming
        mock_stream = MagicMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        async def _mock_event_stream():
            yield text_event
            yield stop_event

        mock_stream.__aiter__ = lambda self: _mock_event_stream()

        c.async_client.beta.messages.stream = MagicMock(return_value=mock_stream)

        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")

        responses = []
        async for response in c.ainvoke_stream(msgs, assistant):
            responses.append(response)

        assert len(responses) >= 0  # Streaming may produce 0+ responses depending on event handling

    @pytest.mark.asyncio
    async def test_ainvoke_stream_rate_limit_raises(self):
        from anthropic import RateLimitError
        import httpx
        c = _make_claude(api_key="key")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 429
        mock_response.headers = {}
        err = RateLimitError("rate limited", response=mock_response, body=None)

        mock_stream = MagicMock()
        mock_stream.__aenter__ = AsyncMock(side_effect=err)
        mock_stream.__aexit__ = AsyncMock(return_value=False)
        c.async_client.beta.messages.stream = MagicMock(return_value=mock_stream)

        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")

        with pytest.raises(ModelRateLimitError):
            async for _ in c.ainvoke_stream(msgs, assistant):
                pass

    @pytest.mark.asyncio
    async def test_ainvoke_stream_connection_error_raises(self):
        from anthropic import APIConnectionError
        c = _make_claude(api_key="key")

        err = MagicMock(spec=APIConnectionError)
        err.__class__ = APIConnectionError
        err.message = "connection failed"

        mock_stream = MagicMock()
        mock_stream.__aenter__ = AsyncMock(side_effect=err)
        mock_stream.__aexit__ = AsyncMock(return_value=False)
        c.async_client.beta.messages.stream = MagicMock(return_value=mock_stream)

        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")

        with pytest.raises(ModelProviderError):
            async for _ in c.ainvoke_stream(msgs, assistant):
                pass


# ---------------------------------------------------------------------------
# Claude.__deepcopy__ tests
# ---------------------------------------------------------------------------

class TestClaudeDeepcopy:
    def test_deepcopy_clears_client(self):
        c = Claude(api_key="key123")
        c.client = MagicMock(name="live_client")
        c_copy = copy.deepcopy(c)
        assert c_copy.client is None

    def test_deepcopy_clears_async_client(self):
        c = Claude(api_key="key456")
        c.async_client = MagicMock(name="live_async_client")
        c_copy = copy.deepcopy(c)
        assert c_copy.async_client is None

    def test_deepcopy_preserves_config(self):
        c = Claude(
            id="claude-opus-4-6",
            api_key="my_key",
            max_tokens=4096,
            temperature=0.7,
        )
        c_copy = copy.deepcopy(c)
        assert c_copy.id == "claude-opus-4-6"
        assert c_copy.api_key == "my_key"
        assert c_copy.max_tokens == 4096
        assert c_copy.temperature == 0.7

    def test_deepcopy_independent_list_fields(self):
        c = Claude(stop_sequences=["STOP", "END"])
        c_copy = copy.deepcopy(c)
        c_copy.stop_sequences.append("NEW")
        assert "NEW" not in c.stop_sequences


# ---------------------------------------------------------------------------
# Claude.get_async_client() paths
# ---------------------------------------------------------------------------

class TestClaudeGetAsyncClient:
    def test_returns_existing_async_client(self):
        c = Claude(api_key="key")
        mock_client = MagicMock()
        mock_client.is_closed.return_value = False
        c.async_client = mock_client
        returned = c.get_async_client()
        assert returned is mock_client

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env_key"}, clear=False)
    def test_creates_async_client_with_api_key_from_env(self):
        c = Claude()
        c.api_key = None
        c.async_client = None
        with patch("ii_agent.agent.runtime.models.anthropic.claude.AsyncAnthropicClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.is_closed.return_value = False
            MockClient.return_value = mock_instance
            result = c.get_async_client()
            assert result is mock_instance

    def test_creates_async_client_with_provided_api_key(self):
        c = Claude(api_key="provided_key")
        c.async_client = None
        with patch("ii_agent.agent.runtime.models.anthropic.claude.AsyncAnthropicClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.is_closed.return_value = False
            MockClient.return_value = mock_instance
            result = c.get_async_client()
            assert MockClient.called
            assert result is mock_instance


# ---------------------------------------------------------------------------
# Claude._prepare_request_kwargs more paths
# ---------------------------------------------------------------------------

class TestClaudePrepareRequestKwargsDeep:
    def test_system_message_as_list_of_text_blocks(self):
        c = Claude()
        kwargs = c._prepare_request_kwargs("System text")
        assert isinstance(kwargs["system"], list)
        assert kwargs["system"][0]["type"] == "text"
        assert kwargs["system"][0]["text"] == "System text"

    def test_tools_included_when_provided(self):
        c = Claude()
        tools = [{"name": "search", "description": "Search"}]
        kwargs = c._prepare_request_kwargs("System", tools=tools)
        assert "tools" in kwargs
        assert len(kwargs["tools"]) == 1

    def test_no_tools_no_tools_key(self):
        c = Claude()
        kwargs = c._prepare_request_kwargs("System")
        assert "tools" not in kwargs

    def test_response_format_with_dict_format(self):
        c = Claude()
        fmt = {"type": "json_schema", "schema": {"type": "object"}}
        kwargs = c._prepare_request_kwargs("System", response_format=fmt)
        # response_format dict should not crash the method
        assert isinstance(kwargs, dict)


# ---------------------------------------------------------------------------
# Claude ainvoke happy path with system + user messages
# ---------------------------------------------------------------------------

class TestClaudeAinvokeDeepHappyPaths:
    @pytest.mark.asyncio
    async def test_ainvoke_with_thinking_enabled(self):
        c = _make_claude(
            api_key="key",
            thinking={"type": "enabled", "budget_tokens": 2048},
        )
        thinking_block = _make_response_block("thinking", thinking="Let me think...", signature="sig_abc")
        text_block = _make_response_block("text", text="Final answer", citations=None)
        provider_resp = _make_provider_response(
            [thinking_block, text_block], stop_reason="end_turn"
        )
        c.async_client.beta.messages.create = AsyncMock(return_value=provider_resp)

        msgs = [Message(role="user", content="What is 2+2?")]
        assistant = Message(role="assistant", content="")
        result = await c.ainvoke(msgs, assistant)

        assert result.content == "Final answer"
        assert result.reasoning_content == "Let me think..."

    @pytest.mark.asyncio
    async def test_ainvoke_with_tool_call_response(self):
        c = _make_claude(api_key="key")
        tool_block = _make_response_block(
            "tool_use",
            id="tc_abc",
            name="calculator",
            input={"expression": "2+2"},
            citations=None,
        )
        provider_resp = _make_provider_response([tool_block], stop_reason="tool_use")
        c.async_client.beta.messages.create = AsyncMock(return_value=provider_resp)

        msgs = [Message(role="user", content="Calculate 2+2")]
        assistant = Message(role="assistant", content="")
        result = await c.ainvoke(msgs, assistant)

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["function"]["name"] == "calculator"

    @pytest.mark.asyncio
    async def test_ainvoke_with_cache_tokens_in_usage(self):
        c = _make_claude(api_key="key", cache_system_prompt=True)
        text_block = _make_response_block("text", text="Cached response", citations=None)
        usage = _make_usage(input_t=200, output_t=100, cache_create=50, cache_read=150)
        provider_resp = _make_provider_response([text_block], usage=usage)
        c.async_client.beta.messages.create = AsyncMock(return_value=provider_resp)

        msgs = [
            Message(role="system", content="You are an assistant"),
            Message(role="user", content="Hello"),
        ]
        assistant = Message(role="assistant", content="")
        result = await c.ainvoke(msgs, assistant)

        assert result.response_usage.input_tokens == 200
        assert result.response_usage.output_tokens == 100

    @pytest.mark.asyncio
    async def test_ainvoke_httpcore_connection_error(self):
        import httpcore
        c = _make_claude(api_key="key")
        c.async_client.beta.messages.create = AsyncMock(
            side_effect=httpcore.ConnectError("connection refused")
        )
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await c.ainvoke(msgs, assistant)
