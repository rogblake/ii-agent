"""Unit tests for chat/llm/gemini.py - GeminiProvider and helpers."""

from __future__ import annotations

import base64
import json
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.chat.llm.gemini import (
    GeminiProvider,
    GeminiStreamState,
    generate_tool_call_id,
    get_thought_signature_from_content,
    get_thought_signature_from_provider_options,
    get_tool_call_from_parts,
    map_googe_finish_reason,
)
from ii_agent.chat.schemas import (
    BinaryContent,
    EventType,
    FinishReason,
    Message,
    MessageRole,
    ReasoningContent,
    RunResponseEvent,
    TextContent,
    ToolCall,
)
from ii_agent.core.config.llm_config import LLMConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_llm_config(model="gemini-pro") -> LLMConfig:
    cfg = MagicMock(spec=LLMConfig)
    cfg.model = model
    cfg.api_key = None
    cfg.vertex_project_id = None
    cfg.vertex_region = None
    cfg.temperature = None
    cfg.setting_id = "test-setting"
    return cfg


def _make_provider(model="gemini-pro") -> GeminiProvider:
    cfg = _make_llm_config(model)
    with patch("ii_agent.chat.llm.gemini.genai") as mock_genai:
        mock_genai.Client.return_value = MagicMock()
        provider = GeminiProvider(cfg)
    provider.client = MagicMock()
    return provider


def _make_text_message(text: str, role=MessageRole.USER) -> Message:
    msg = MagicMock(spec=Message)
    msg.role = role
    msg.parts = [TextContent(text=text)]
    msg.tool_results = MagicMock(return_value=[])
    msg.tool_calls = MagicMock(return_value=[])
    return msg


# ---------------------------------------------------------------------------
# map_googe_finish_reason
# ---------------------------------------------------------------------------

class TestMapGoogeFinishReason:
    def test_stop_maps_to_end_turn(self):
        assert map_googe_finish_reason("STOP", False) == FinishReason.END_TURN

    def test_max_tokens_maps(self):
        assert map_googe_finish_reason("MAX_TOKENS", False) == FinishReason.MAX_TOKENS

    def test_safety_maps_to_error(self):
        assert map_googe_finish_reason("SAFETY", False) == FinishReason.ERROR

    def test_recitation_maps_to_error(self):
        assert map_googe_finish_reason("RECITATION", False) == FinishReason.ERROR

    def test_unknown_reason_maps_to_unknown(self):
        assert map_googe_finish_reason("SOMETHING_NEW", False) == FinishReason.UNKNOWN

    def test_stop_with_tool_calls_maps_to_tool_use(self):
        assert map_googe_finish_reason("STOP", True) == FinishReason.TOOL_USE

    def test_max_tokens_with_tool_calls_stays_max_tokens(self):
        assert map_googe_finish_reason("MAX_TOKENS", True) == FinishReason.MAX_TOKENS


# ---------------------------------------------------------------------------
# generate_tool_call_id
# ---------------------------------------------------------------------------

class TestGenerateToolCallId:
    def test_starts_with_call_prefix(self):
        id_ = generate_tool_call_id()
        assert id_.startswith("call_")

    def test_unique_ids(self):
        ids = {generate_tool_call_id() for _ in range(50)}
        assert len(ids) == 50


# ---------------------------------------------------------------------------
# get_thought_signature_from_content / provider_options
# ---------------------------------------------------------------------------

class TestThoughtSignatureHelpers:
    def test_get_from_content_with_signature(self):
        part = MagicMock()
        part.thought_signature = b"\x01\x02\x03"
        result = get_thought_signature_from_content(part)
        expected = base64.b64encode(b"\x01\x02\x03").decode("utf-8")
        assert result == expected

    def test_get_from_content_without_attribute(self):
        part = MagicMock(spec=[])  # no thought_signature attr
        result = get_thought_signature_from_content(part)
        assert result == ""

    def test_get_from_content_with_none_signature(self):
        part = MagicMock()
        part.thought_signature = None
        result = get_thought_signature_from_content(part)
        assert result == ""

    def test_get_from_provider_options_with_signature(self):
        sig_bytes = b"\xde\xad\xbe\xef"
        sig_b64 = base64.b64encode(sig_bytes).decode("utf-8")
        opts = {"google": {"thoughtSignature": sig_b64}}
        result = get_thought_signature_from_provider_options(opts)
        assert result == sig_bytes

    def test_get_from_provider_options_none(self):
        result = get_thought_signature_from_provider_options(None)
        assert result is None

    def test_get_from_provider_options_no_google_key(self):
        result = get_thought_signature_from_provider_options({"other": {}})
        assert result is None

    def test_get_from_provider_options_no_thought_signature(self):
        result = get_thought_signature_from_provider_options({"google": {}})
        assert result is None


# ---------------------------------------------------------------------------
# get_tool_call_from_parts
# ---------------------------------------------------------------------------

class TestGetToolCallFromParts:
    def test_no_function_calls_returns_empty(self):
        parts = [MagicMock(function_call=None), MagicMock(function_call=None)]
        result = get_tool_call_from_parts(parts)
        assert result == []

    def test_one_function_call_returns_tool_call(self):
        fc = MagicMock()
        fc.name = "search_web"
        fc.args = {"query": "python"}
        part = MagicMock()
        part.function_call = fc
        part.thought_signature = None

        calls = get_tool_call_from_parts([part])
        assert len(calls) == 1
        assert calls[0].name == "search_web"
        assert calls[0].finished is True

    def test_multiple_function_calls(self):
        parts = []
        for i in range(3):
            fc = MagicMock()
            fc.name = f"tool_{i}"
            fc.args = {}
            p = MagicMock()
            p.function_call = fc
            p.thought_signature = None
            parts.append(p)

        calls = get_tool_call_from_parts(parts)
        assert len(calls) == 3


# ---------------------------------------------------------------------------
# GeminiProvider._convert_tools
# ---------------------------------------------------------------------------

class TestConvertTools:
    def test_none_tools_returns_none(self):
        provider = _make_provider()
        assert provider._convert_tools(None) is None

    def test_empty_tools_returns_none(self):
        provider = _make_provider()
        assert provider._convert_tools([]) is None

    def test_converts_function_type_tool(self):
        provider = _make_provider()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search the web",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = provider._convert_tools(tools)
        assert result is not None
        assert len(result) == 1

    def test_non_function_type_tool_ignored(self):
        provider = _make_provider()
        tools = [{"type": "other", "function": {"name": "x", "description": "y", "parameters": {}}}]
        # Non-function tools are excluded from function_declarations
        with patch("ii_agent.chat.llm.gemini.types") as mock_types:
            mock_types.Tool.return_value = MagicMock()
            mock_types.FunctionDeclaration.return_value = MagicMock()
            result = provider._convert_tools(tools)
        # No function declarations => returns None
        assert result is None


# ---------------------------------------------------------------------------
# GeminiProvider._add_code_execution_tool
# ---------------------------------------------------------------------------

class TestAddCodeExecutionTool:
    def test_adds_to_empty_list(self):
        provider = _make_provider()
        with patch("ii_agent.chat.llm.gemini.types") as mock_types:
            mock_types.Tool.return_value = MagicMock()
            mock_types.ToolCodeExecution.return_value = MagicMock()
            result = provider._add_code_execution_tool(None)
        assert len(result) == 1

    def test_appends_to_existing_list(self):
        provider = _make_provider()
        existing = [MagicMock()]
        with patch("ii_agent.chat.llm.gemini.types") as mock_types:
            mock_types.Tool.return_value = MagicMock()
            mock_types.ToolCodeExecution.return_value = MagicMock()
            result = provider._add_code_execution_tool(existing)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# GeminiProvider._convert_messages
# ---------------------------------------------------------------------------

class TestConvertMessages:
    def test_empty_messages_returns_empty(self):
        provider = _make_provider()
        with patch("ii_agent.chat.llm.gemini.types") as mock_types:
            mock_types.Content.return_value = MagicMock()
            mock_types.Part.return_value = MagicMock()
            result = provider._convert_messages([])
        assert result == []

    def test_user_text_message_creates_user_content(self):
        provider = _make_provider()
        msg = _make_text_message("hello", role=MessageRole.USER)

        with patch("ii_agent.chat.llm.gemini.types") as mock_types:
            mock_types.Content.return_value = MagicMock()
            mock_types.Part.return_value = MagicMock()
            result = provider._convert_messages([msg])
        assert len(result) == 1

    def test_user_binary_message_handled(self):
        provider = _make_provider()
        binary = MagicMock(spec=BinaryContent)
        binary.mime_type = "image/png"
        binary.data = b"\x89PNG"

        msg = MagicMock(spec=Message)
        msg.role = MessageRole.USER
        msg.parts = [binary]
        msg.tool_results = MagicMock(return_value=[])

        with patch("ii_agent.chat.llm.gemini.types") as mock_types:
            mock_types.Content.return_value = MagicMock()
            mock_types.Part.return_value = MagicMock()
            mock_types.Blob.return_value = MagicMock()
            result = provider._convert_messages([msg])

        assert len(result) == 1

    def test_tool_message_creates_function_response(self):
        provider = _make_provider()

        tool_result = MagicMock()
        tool_result.name = "search"
        tool_result.output = MagicMock()
        tool_result.output.model_dump.return_value = {"result": "found"}

        msg = MagicMock(spec=Message)
        msg.role = MessageRole.TOOL
        msg.parts = []
        msg.tool_results = MagicMock(return_value=[tool_result])

        with patch("ii_agent.chat.llm.gemini.types") as mock_types:
            mock_types.Content.return_value = MagicMock()
            mock_types.Part.return_value = MagicMock()
            mock_types.FunctionResponse.return_value = MagicMock()
            result = provider._convert_messages([msg])

        assert len(result) == 1

    def test_tool_message_with_no_results_skips(self):
        provider = _make_provider()

        msg = MagicMock(spec=Message)
        msg.role = MessageRole.TOOL
        msg.parts = []
        msg.tool_results = MagicMock(return_value=[])

        with patch("ii_agent.chat.llm.gemini.types"):
            result = provider._convert_messages([msg])

        assert result == []

    def test_unknown_role_skips_message(self):
        provider = _make_provider()

        msg = MagicMock(spec=Message)
        msg.role = "unknown_role"
        msg.parts = []
        msg.tool_results = MagicMock(return_value=[])

        with patch("ii_agent.chat.llm.gemini.types"):
            result = provider._convert_messages([msg])

        assert result == []


# ---------------------------------------------------------------------------
# GeminiProvider.model
# ---------------------------------------------------------------------------

class TestGeminiProviderModel:
    def test_model_returns_dict_with_name(self):
        provider = _make_provider("gemini-ultra")
        info = provider.model()
        assert info["id"] == "gemini-ultra"
        assert info["name"] == "gemini-ultra"


# ---------------------------------------------------------------------------
# GeminiStreamState
# ---------------------------------------------------------------------------

class TestGeminiStreamState:
    def test_initial_state(self):
        parts = []
        state = GeminiStreamState(content_parts=parts)
        assert state.current_block is None
        assert state.accumulated_text == ""
        assert state.accumulated_thinking == ""
        assert state.has_tool_calls is False

    def test_handle_text_emits_content_events(self):
        parts = []
        state = GeminiStreamState(content_parts=parts)

        part = MagicMock()
        part.text = "hello"
        part.thought = False
        part.thought_signature = None

        events = state.handle_text_or_reasoning_part(part)
        # Should have CONTENT_START and CONTENT_DELTA
        event_types = [e.type for e in events]
        assert EventType.CONTENT_START in event_types
        assert EventType.CONTENT_DELTA in event_types

    def test_handle_reasoning_emits_thinking_events(self):
        parts = []
        state = GeminiStreamState(content_parts=parts)

        part = MagicMock()
        part.text = "thinking..."
        part.thought = True
        part.thought_signature = None

        events = state.handle_text_or_reasoning_part(part)
        event_types = [e.type for e in events]
        assert EventType.THINKING_START in event_types
        assert EventType.THINKING_DELTA in event_types

    def test_transition_from_text_to_reasoning_closes_text(self):
        parts = []
        state = GeminiStreamState(content_parts=parts)
        state.current_block = "text"
        state.accumulated_text = "some text"

        part = MagicMock()
        part.text = "thinking"
        part.thought = True
        part.thought_signature = None

        events = state.handle_text_or_reasoning_part(part)
        event_types = [e.type for e in events]
        # Should close text block (CONTENT_STOP) then open thinking
        assert EventType.CONTENT_STOP in event_types
        assert EventType.THINKING_START in event_types

    def test_transition_from_reasoning_to_text_closes_reasoning(self):
        parts = []
        state = GeminiStreamState(content_parts=parts)
        state.current_block = "reasoning"
        state.accumulated_thinking = "some thought"

        part = MagicMock()
        part.text = "text"
        part.thought = False
        part.thought_signature = None

        events = state.handle_text_or_reasoning_part(part)
        event_types = [e.type for e in events]
        assert EventType.THINKING_STOP in event_types
        assert EventType.CONTENT_START in event_types

    def test_handle_tool_calls_emits_tool_events(self):
        parts = []
        state = GeminiStreamState(content_parts=parts)

        fc = MagicMock()
        fc.name = "search"
        fc.args = {}
        tool_part = MagicMock()
        tool_part.function_call = fc
        tool_part.thought_signature = None

        events = state.handle_tool_calls([tool_part])
        event_types = [e.type for e in events]
        assert EventType.TOOL_USE_START in event_types
        assert EventType.TOOL_USE_DELTA in event_types
        assert EventType.TOOL_USE_STOP in event_types
        assert state.has_tool_calls is True
        assert len(parts) == 1

    def test_handle_tool_calls_no_function_calls_returns_empty(self):
        parts = []
        state = GeminiStreamState(content_parts=parts)

        non_tool_part = MagicMock()
        non_tool_part.function_call = None
        events = state.handle_tool_calls([non_tool_part])
        assert events == []

    def test_flush_text_block(self):
        parts = []
        state = GeminiStreamState(content_parts=parts)
        state.current_block = "text"
        state.accumulated_text = "accumulated text"

        events = state.flush()
        event_types = [e.type for e in events]
        assert EventType.CONTENT_STOP in event_types
        assert len(parts) == 1  # TextContent added
        assert isinstance(parts[0], TextContent)

    def test_flush_reasoning_block(self):
        parts = []
        state = GeminiStreamState(content_parts=parts)
        state.current_block = "reasoning"
        state.accumulated_thinking = "my thinking"

        events = state.flush()
        event_types = [e.type for e in events]
        assert EventType.THINKING_STOP in event_types
        assert len(parts) == 1  # ReasoningContent added
        assert isinstance(parts[0], ReasoningContent)

    def test_flush_with_no_active_block_returns_empty(self):
        parts = []
        state = GeminiStreamState(content_parts=parts)
        events = state.flush()
        assert events == []

    def test_close_text_block_with_signature(self):
        parts = []
        state = GeminiStreamState(content_parts=parts)
        state.current_block = "text"
        state.accumulated_text = "hello"
        state.last_text_signature = "sig123"

        events = state._close_text_block()
        assert len(parts) == 1
        assert parts[0].provider_options == {"google": {"thoughtSignature": "sig123"}}

    def test_close_reasoning_block_with_signature(self):
        parts = []
        state = GeminiStreamState(content_parts=parts)
        state.current_block = "reasoning"
        state.accumulated_thinking = "deep thought"
        state.last_thinking_signature = "sig456"

        events = state._close_reasoning_block()
        assert len(parts) == 1
        assert parts[0].provider_options == {"google": {"thoughtSignature": "sig456"}}

    def test_text_accumulates_across_multiple_parts(self):
        parts = []
        state = GeminiStreamState(content_parts=parts)

        for i in range(3):
            part = MagicMock()
            part.text = f"chunk{i}"
            part.thought = False
            part.thought_signature = None
            state.handle_text_or_reasoning_part(part)

        assert state.accumulated_text == "chunk0chunk1chunk2"
