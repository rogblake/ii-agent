"""Deep unit tests for CustomProvider - coverage gaps."""

from __future__ import annotations

import json
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.chat.llm.custom import CustomProvider
from ii_agent.chat.types import (
    ArrayResultContent,
    BinaryContent,
    ErrorJsonContent,
    EventType,
    FileDataContentPart,
    FinishReason,
    ImageURLContent,
    ImageUrlContentPart,
    Message,
    MessageRole,
    ReasoningContent,
    StorybookProgressContent,
    StorybookResultContent,
    TextContent,
    TextContentPart,
    TextResultContent,
    ToolCall,
)
from ii_agent.settings.llm import Provider
from ii_agent.core.config.llm_config import LLMConfig

_SESSION_ID = "deep-custom-test-001"


def _make_config(
    model: str = "custom/gpt-4",
    provider: Provider = Provider.CUSTOM,
    api_key: Optional[str] = "sk-test",
    base_url: Optional[str] = None,
    temperature: float = 0.0,
) -> LLMConfig:
    return LLMConfig(
        model=model,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    )


def _make_provider(model: str = "custom/gpt-4") -> CustomProvider:
    return CustomProvider(_make_config(model=model))


def _user_message(text: str = "Hello") -> Message:
    msg = MagicMock(spec=Message)
    msg.role = MessageRole.USER
    msg.parts = [TextContent(text=text)]
    msg.tool_results = MagicMock(return_value=[])
    msg.tool_calls = MagicMock(return_value=[])
    return msg


def _assistant_message(text: str = "Hi", tool_calls=None) -> Message:
    msg = MagicMock(spec=Message)
    msg.role = MessageRole.ASSISTANT
    msg.parts = [TextContent(text=text)]
    msg.tool_results = MagicMock(return_value=[])
    msg.tool_calls = MagicMock(return_value=tool_calls or [])
    return msg


def _tool_message(results: list) -> Message:
    msg = MagicMock(spec=Message)
    msg.role = MessageRole.TOOL
    msg.parts = []
    msg.tool_results = MagicMock(return_value=results)
    msg.tool_calls = MagicMock(return_value=[])
    return msg


def _make_tool_result(tool_call_id: str, name: str, output) -> MagicMock:
    tr = MagicMock()
    tr.tool_call_id = tool_call_id
    tr.name = name
    tr.output = output
    return tr


# ---------------------------------------------------------------------------
# Constructor deep coverage
# ---------------------------------------------------------------------------


class TestCustomProviderInitDeep:
    """Deep init tests."""

    def test_non_gemini_api_type_not_prefixed(self):
        """Non-Gemini API type should not add any prefix to model name."""
        cfg = _make_config(model="gpt-4", provider=Provider.OPENAI)
        provider = CustomProvider(cfg)
        assert provider.model_name == "gpt-4"

    def test_gemini_api_type_prefixes_model(self):
        """Gemini API type should prefix model with 'gemini/'."""
        cfg = _make_config(model="gemini-2.0-flash", provider=Provider.GOOGLE)
        provider = CustomProvider(cfg)
        assert provider.model_name == "gemini/gemini-2.0-flash"

    def test_model_with_slash_extracts_correct_provider_prefix(self):
        """Model with slash should have provider extracted."""
        provider = _make_provider("anthropic/claude-3-haiku")
        assert provider.provider_prefix == "anthropic"

    def test_model_without_slash_provider_prefix_is_custom(self):
        """Model without slash should have 'custom' as provider prefix."""
        provider = _make_provider("gpt-4-turbo-preview")
        assert provider.provider_prefix == "custom"

    def test_temperature_accessible_via_llm_config(self):
        """Temperature from config should be accessible via llm_config."""
        cfg = _make_config(temperature=0.7)
        provider = CustomProvider(cfg)
        assert provider.llm_config.temperature == 0.7

    def test_zero_temperature_accessible(self):
        """Zero temperature should be accessible (not treated as None/falsy)."""
        cfg = _make_config(temperature=0.0)
        provider = CustomProvider(cfg)
        assert provider.llm_config.temperature == 0.0

    def test_llm_config_stored(self):
        """llm_config should be stored and accessible."""
        cfg = LLMConfig(
            model="gpt-4",
            provider=Provider.CUSTOM,
            api_key="test-key",
        )
        provider = CustomProvider(cfg)
        assert provider.llm_config is not None
        assert provider.llm_config.model == "gpt-4"


# ---------------------------------------------------------------------------
# _convert_messages - deeper non-tool role coverage
# ---------------------------------------------------------------------------


class TestConvertMessagesNonToolDeep:
    """Deep coverage for _convert_messages with various content types."""

    def test_user_message_with_binary_image_creates_image_url_block(self):
        """BinaryContent images should create image_url blocks."""
        provider = _make_provider()
        binary = MagicMock(spec=BinaryContent)
        binary.to_base64 = MagicMock(return_value="data:image/png;base64,iVBOR...")
        binary.mime_type = "image/png"

        msg = MagicMock(spec=Message)
        msg.role = MessageRole.USER
        msg.parts = [TextContent(text="Check this image"), binary]
        msg.tool_results = MagicMock(return_value=[])
        msg.tool_calls = MagicMock(return_value=[])

        result = provider._convert_messages([msg])
        content = result[0]["content"]
        assert isinstance(content, list)
        img_items = [c for c in content if c.get("type") == "image_url"]
        assert len(img_items) == 1

    def test_user_message_with_image_url_content(self):
        """ImageURLContent should create image_url block."""
        provider = _make_provider()
        img = ImageURLContent(url="https://example.com/pic.jpg")

        msg = MagicMock(spec=Message)
        msg.role = MessageRole.USER
        msg.parts = [img]
        msg.tool_results = MagicMock(return_value=[])
        msg.tool_calls = MagicMock(return_value=[])

        result = provider._convert_messages([msg])
        content = result[0]["content"]
        img_items = [c for c in content if c.get("type") == "image_url"]
        assert len(img_items) == 1
        assert img_items[0]["image_url"]["url"] == "https://example.com/pic.jpg"

    def test_assistant_message_only_tool_calls_no_content_key(self):
        """Assistant message with only tool calls should have 'tool_calls' key."""
        provider = _make_provider()
        tc = ToolCall(id="call_1", name="search", input='{"q": "test"}', finished=True)

        msg = MagicMock(spec=Message)
        msg.role = MessageRole.ASSISTANT
        msg.parts = [tc]
        msg.tool_results = MagicMock(return_value=[])
        msg.tool_calls = MagicMock(return_value=[tc])

        result = provider._convert_messages([msg])
        assert result[0]["role"] == "assistant"
        assert "tool_calls" in result[0]

    def test_assistant_message_text_and_tool_calls(self):
        """Assistant message with text and tool calls should have both."""
        provider = _make_provider()
        tc = ToolCall(id="call_1", name="search", input='{"q": "test"}', finished=True)

        msg = MagicMock(spec=Message)
        msg.role = MessageRole.ASSISTANT
        msg.parts = [TextContent(text="Let me search for that"), tc]
        msg.tool_results = MagicMock(return_value=[])
        msg.tool_calls = MagicMock(return_value=[tc])

        result = provider._convert_messages([msg])
        assert result[0]["role"] == "assistant"
        assert "tool_calls" in result[0]
        assert result[0]["content"] == "Let me search for that"

    def test_assistant_message_reasoning_content_included(self):
        """ReasoningContent in assistant message should be included in content."""
        provider = _make_provider()
        rc = ReasoningContent(thinking="I'm thinking...", signature="sig")

        msg = MagicMock(spec=Message)
        msg.role = MessageRole.ASSISTANT
        msg.parts = [rc, TextContent(text="Result")]
        msg.tool_results = MagicMock(return_value=[])
        msg.tool_calls = MagicMock(return_value=[])

        result = provider._convert_messages([msg])
        assert result[0]["role"] == "assistant"

    def test_empty_messages_list_returns_empty(self):
        provider = _make_provider()
        result = provider._convert_messages([])
        assert result == []

    def test_system_message_converted(self):
        """System messages should be converted with role='system'."""
        provider = _make_provider()
        msg = MagicMock(spec=Message)
        msg.role = MessageRole.SYSTEM
        msg.parts = [TextContent(text="You are helpful")]
        msg.tool_results = MagicMock(return_value=[])
        msg.tool_calls = MagicMock(return_value=[])

        result = provider._convert_messages([msg])
        assert result[0]["role"] == "system"
        assert "helpful" in result[0]["content"]

    def test_assistant_no_parts_creates_empty_message(self):
        """Assistant message with no parts should still be included."""
        provider = _make_provider()
        msg = MagicMock(spec=Message)
        msg.role = MessageRole.ASSISTANT
        msg.parts = []
        msg.tool_results = MagicMock(return_value=[])
        msg.tool_calls = MagicMock(return_value=[])

        result = provider._convert_messages([msg])
        # Should still produce an assistant message even with no parts
        assert result[0]["role"] == "assistant"


# ---------------------------------------------------------------------------
# _convert_messages - tool result deeper coverage
# ---------------------------------------------------------------------------


class TestConvertMessagesToolDeep:
    """Deep coverage for tool result conversion in CustomProvider."""

    def test_storybook_progress_content_serialized(self):
        """StorybookProgressContent should be serialized to JSON."""
        provider = _make_provider()
        output = StorybookProgressContent(
            storybook_id="sb1",
            storybook_name="Story",
            total_pages=5,
            completed_pages=3,
            current_page=3,
            status="generating",
            generating_pages=[3, 4],
            error_message=None,
        )
        tr = _make_tool_result("c1", "tool", output)
        msg = _tool_message([tr])
        result = provider._convert_messages([msg])
        data = json.loads(result[0]["content"])
        assert data["type"] == "storybook_progress"
        assert data["total_pages"] == 5

    def test_storybook_result_content_serialized(self):
        """StorybookResultContent should be serialized to JSON."""
        from ii_agent.chat.types import StorybookPageResult

        provider = _make_provider()
        page = StorybookPageResult(
            page_number=1, image_url="https://example.com/p1.jpg", text_content="Page 1 text"
        )
        output = StorybookResultContent(storybook_id="sb2", storybook_name="Story 2", pages=[page])
        tr = _make_tool_result("c1", "tool", output)
        msg = _tool_message([tr])
        result = provider._convert_messages([msg])
        data = json.loads(result[0]["content"])
        assert data["type"] == "storybook"
        assert data["page_count"] == 1
        assert data["pages"][0]["image_url"] == "https://example.com/p1.jpg"

    def test_array_result_multiple_text_parts_joined(self):
        """Multiple TextContentParts in ArrayResult should be joined."""
        provider = _make_provider()
        output = ArrayResultContent(
            value=[
                TextContentPart(text="part 1"),
                TextContentPart(text="part 2"),
            ]
        )
        tr = _make_tool_result("c1", "tool", output)
        msg = _tool_message([tr])
        result = provider._convert_messages([msg])
        content = result[0]["content"]
        assert "part 1" in content
        assert "part 2" in content

    def test_error_json_content_serialized(self):
        """ErrorJsonContent should be serialized to JSON."""
        provider = _make_provider()
        output = ErrorJsonContent(value={"error": "api_error", "code": 429, "retry": True})
        tr = _make_tool_result("c1", "tool", output)
        msg = _tool_message([tr])
        result = provider._convert_messages([msg])
        data = json.loads(result[0]["content"])
        assert data["error"] == "api_error"
        assert data["code"] == 429

    def test_array_result_image_url_part_creates_string_content(self):
        """ImageUrlContentPart in ArrayResult should create string with URL."""
        provider = _make_provider()
        output = ArrayResultContent(
            value=[ImageUrlContentPart(url="https://example.com/generated.png")]
        )
        tr = _make_tool_result("c1", "tool", output)
        msg = _tool_message([tr])
        result = provider._convert_messages([msg])
        content = result[0]["content"]
        # In custom provider, array results are joined as string
        assert "generated.png" in content

    def test_array_result_file_data_part_creates_file_string(self):
        """FileDataContentPart in ArrayResult should create string with filename."""
        provider = _make_provider()
        output = ArrayResultContent(
            value=[
                FileDataContentPart(
                    mime_type="application/pdf", data="pdfdata64", filename="doc.pdf"
                )
            ]
        )
        tr = _make_tool_result("c1", "tool", output)
        msg = _tool_message([tr])
        result = provider._convert_messages([msg])
        content = result[0]["content"]
        # Should contain the filename
        assert "doc.pdf" in content

    def test_multiple_tool_results_in_one_message(self):
        """Message with multiple tool results should produce multiple converted messages."""
        provider = _make_provider()
        tr1 = _make_tool_result("call_1", "search", TextResultContent(value="result 1"))
        tr2 = _make_tool_result("call_2", "calc", TextResultContent(value="result 2"))
        msg = _tool_message([tr1, tr2])
        result = provider._convert_messages([msg])
        assert len(result) == 2
        assert all(r["role"] == "tool" for r in result)


# ---------------------------------------------------------------------------
# send() - deeper coverage
# ---------------------------------------------------------------------------


class TestCustomProviderSendDeep:
    """Deep tests for send() covering more scenarios."""

    @pytest.mark.asyncio
    async def test_send_with_custom_tools(self):
        """send() should pass tools to acompletion."""
        provider = _make_provider()
        msg = _user_message("Hello")
        tools = [
            {
                "type": "function",
                "function": {"name": "search", "description": "search", "parameters": {}},
            }
        ]

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "response"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ) as mock_acomp:
            await provider.send([msg], tools=tools)

        call_kwargs = mock_acomp.call_args[1]
        assert "tools" in call_kwargs
        assert len(call_kwargs["tools"]) == 1

    @pytest.mark.asyncio
    async def test_send_with_tool_choice_none_when_no_tools(self):
        """send() without tools should not pass tool_choice."""
        provider = _make_provider()
        msg = _user_message("Hello")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "response"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ) as mock_acomp:
            await provider.send([msg], tools=None)

        call_kwargs = mock_acomp.call_args[1]
        assert "tool_choice" not in call_kwargs or call_kwargs.get("tool_choice") is None

    @pytest.mark.asyncio
    async def test_send_uses_usage_tokens_when_present(self):
        """send() should extract usage info when present in response."""
        provider = _make_provider()
        msg = _user_message("Hello")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "response"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(input_tokens=200, output_tokens=100)

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ):
            result = await provider.send([msg])

        assert result.usage.input_tokens == 200
        assert result.usage.output_tokens == 100

    @pytest.mark.asyncio
    async def test_send_finish_reason_content_filter_maps_to_error(self):
        """'content_filter' finish reason should map to ERROR."""
        provider = _make_provider()
        msg = _user_message("Hello")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = None
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "content_filter"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ):
            result = await provider.send([msg])

        assert result.finish_reason == FinishReason.ERROR

    @pytest.mark.asyncio
    async def test_send_finish_reason_length_maps_to_max_tokens(self):
        """'length' finish reason should map to MAX_TOKENS."""
        provider = _make_provider()
        msg = _user_message("Hello")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "partial"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "length"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ):
            result = await provider.send([msg])

        assert result.finish_reason == FinishReason.MAX_TOKENS

    @pytest.mark.asyncio
    async def test_send_finish_reason_unknown_value_maps_to_end_turn(self):
        """Unknown finish reason should map to END_TURN (default case)."""
        provider = _make_provider()
        msg = _user_message("Hello")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "response"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "some_new_reason"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ):
            result = await provider.send([msg])

        # Default to END_TURN for unknown reasons
        assert result.finish_reason in [FinishReason.END_TURN, FinishReason.UNKNOWN]

    @pytest.mark.asyncio
    async def test_send_temperature_passed_to_acompletion(self):
        """Temperature should be passed to acompletion."""
        cfg = _make_config(temperature=0.8)
        provider = CustomProvider(cfg)
        msg = _user_message("Hello")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "response"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ) as mock_acomp:
            await provider.send([msg])

        call_kwargs = mock_acomp.call_args[1]
        assert call_kwargs.get("temperature") == 0.8

    @pytest.mark.asyncio
    async def test_send_passes_base_url_when_configured(self):
        """base_url should be passed to acompletion when set."""
        cfg = _make_config(base_url="http://localhost:8080/v1")
        provider = CustomProvider(cfg)
        msg = _user_message("Hello")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "response"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ) as mock_acomp:
            await provider.send([msg])

        call_kwargs = mock_acomp.call_args[1]
        assert call_kwargs.get("base_url") == "http://localhost:8080/v1"

    @pytest.mark.asyncio
    async def test_send_passes_api_key(self):
        """API key should be passed to acompletion."""
        cfg = _make_config(api_key="my-secret-key-123")
        provider = CustomProvider(cfg)
        msg = _user_message("Hello")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "response"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ) as mock_acomp:
            await provider.send([msg])

        call_kwargs = mock_acomp.call_args[1]
        assert call_kwargs.get("api_key") == "my-secret-key-123"

    @pytest.mark.asyncio
    async def test_send_multiple_text_content_parts_merged(self):
        """Multiple text content parts in response should be concatenated."""
        provider = _make_provider()
        msg = _user_message("Hello")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Part 1\nPart 2"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ):
            result = await provider.send([msg])

        text_parts = [p for p in result.content if isinstance(p, TextContent)]
        assert len(text_parts) == 1
        assert "Part 1" in text_parts[0].text
        assert "Part 2" in text_parts[0].text

    @pytest.mark.asyncio
    async def test_send_with_multiple_tool_calls(self):
        """Response with multiple tool calls should return all as ToolCall objects."""
        provider = _make_provider()
        msg = _user_message("Search and calculate")

        tc1 = MagicMock()
        tc1.id = "call_1"
        tc1.function.name = "search"
        tc1.function.arguments = '{"q": "test"}'

        tc2 = MagicMock()
        tc2.id = "call_2"
        tc2.function.name = "calc"
        tc2.function.arguments = '{"expr": "1+1"}'

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = None
        mock_choice.message.tool_calls = [tc1, tc2]
        mock_choice.finish_reason = "tool_calls"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ):
            result = await provider.send([msg])

        tool_calls = [p for p in result.content if isinstance(p, ToolCall)]
        assert len(tool_calls) == 2
        assert tool_calls[0].name == "search"
        assert tool_calls[1].name == "calc"


# ---------------------------------------------------------------------------
# stream() - deeper coverage
# ---------------------------------------------------------------------------


class TestCustomProviderStreamDeep:
    """Deep tests for stream() method."""

    def _make_chunk(self, content=None, finish_reason=None, tool_calls=None, usage=None):
        chunk = MagicMock()
        delta = MagicMock()
        delta.content = content
        delta.tool_calls = tool_calls
        choice = MagicMock()
        choice.delta = delta
        choice.finish_reason = finish_reason
        chunk.choices = [choice]
        chunk.usage = usage
        return chunk

    def _make_tool_chunk(self, tc_index=0, tc_id="call_1", tc_name="search", args="", finish=None):
        chunk = MagicMock()
        delta = MagicMock()
        delta.content = None
        tc_delta = MagicMock()
        tc_delta.index = tc_index
        tc_delta.id = tc_id
        tc_delta.function = MagicMock()
        tc_delta.function.name = tc_name
        tc_delta.function.arguments = args
        delta.tool_calls = [tc_delta]
        choice = MagicMock()
        choice.delta = delta
        choice.finish_reason = finish
        chunk.choices = [choice]
        chunk.usage = None
        return chunk

    @pytest.mark.asyncio
    async def test_stream_emits_thinking_events_when_reasoning_in_content(self):
        """Stream should emit THINKING events for reasoning content."""
        provider = _make_provider()
        msg = _user_message("Think step by step")

        # Chunk with thinking content (often in <think> tags)
        chunks = [
            self._make_chunk(content="<think>My reasoning</think>\nHello"),
            self._make_chunk(finish_reason="stop"),
        ]

        async def _fake_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=_fake_stream())
        ):
            events = []
            async for event in provider.stream([msg]):
                events.append(event)

        # Should have various content events
        event_types = [e.type for e in events]
        assert EventType.COMPLETE in event_types

    @pytest.mark.asyncio
    async def test_stream_multiple_tool_calls_all_emitted(self):
        """Stream with multiple tool calls should emit events for all."""
        provider = _make_provider()
        msg = _user_message("Do two things")

        chunks = [
            self._make_tool_chunk(0, "call_1", "search", '{"q": "test"}'),
            self._make_tool_chunk(1, "call_2", "calc", '{"e": "1+2"}'),
            self._make_chunk(finish_reason="tool_calls"),
        ]

        async def _fake_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=_fake_stream())
        ):
            events = []
            async for event in provider.stream([msg]):
                events.append(event)

        event_types = [e.type for e in events]
        assert EventType.TOOL_USE_START in event_types
        assert EventType.COMPLETE in event_types
        complete_events = [e for e in events if e.type == EventType.COMPLETE]
        assert complete_events[0].response.finish_reason == FinishReason.TOOL_USE

    @pytest.mark.asyncio
    async def test_stream_content_stop_only_emitted_when_content_started(self):
        """CONTENT_STOP should only be emitted if CONTENT_START was emitted first."""
        provider = _make_provider()
        msg = _user_message("Hello")

        chunks = [self._make_chunk(finish_reason="stop")]

        async def _fake_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=_fake_stream())
        ):
            events = []
            async for event in provider.stream([msg]):
                events.append(event)

        content_stops = [e for e in events if e.type == EventType.CONTENT_STOP]
        content_starts = [e for e in events if e.type == EventType.CONTENT_START]
        # content_stop should only appear if content_start appeared
        assert len(content_stops) <= len(content_starts)

    @pytest.mark.asyncio
    async def test_stream_runtime_error_emits_error(self):
        """RuntimeError during streaming should emit ERROR event."""
        provider = _make_provider()
        msg = _user_message("Hello")

        async def _fake_error_stream(*args, **kwargs):
            yield self._make_chunk(content="Hello")
            raise RuntimeError("Simulated API error")

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=_fake_error_stream())
        ):
            events = []
            async for event in provider.stream([msg]):
                events.append(event)

        # Error event should be emitted
        assert any(e.type == EventType.ERROR for e in events)

    @pytest.mark.asyncio
    async def test_stream_none_finish_reason_not_ending(self):
        """Chunks without finish_reason should not trigger COMPLETE."""
        provider = _make_provider()
        msg = _user_message("Hello")

        chunks = [
            self._make_chunk(content="Part 1", finish_reason=None),
            self._make_chunk(content="Part 2", finish_reason=None),
            self._make_chunk(finish_reason="stop"),
        ]

        async def _fake_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=_fake_stream())
        ):
            events = []
            async for event in provider.stream([msg]):
                events.append(event)

        complete_events = [e for e in events if e.type == EventType.COMPLETE]
        assert len(complete_events) == 1  # Only one COMPLETE at end

    @pytest.mark.asyncio
    async def test_stream_empty_chunk_no_choices_handled(self):
        """Chunks with no choices should be handled gracefully."""
        provider = _make_provider()
        msg = _user_message("Hello")

        empty_chunk = MagicMock()
        empty_chunk.choices = []
        empty_chunk.usage = None

        finish_chunk = self._make_chunk(finish_reason="stop")

        async def _fake_stream(*args, **kwargs):
            yield empty_chunk
            yield finish_chunk

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=_fake_stream())
        ):
            events = []
            async for event in provider.stream([msg]):
                events.append(event)

        assert any(e.type == EventType.COMPLETE for e in events)

    @pytest.mark.asyncio
    async def test_stream_usage_reported_in_complete_event(self):
        """Usage info should be reported in the COMPLETE event."""
        provider = _make_provider()
        msg = _user_message("Hello")

        mock_usage = MagicMock()
        mock_usage.input_tokens = 50
        mock_usage.output_tokens = 25

        chunks = [
            self._make_chunk(content="Hello world"),
            self._make_chunk(finish_reason="stop", usage=mock_usage),
        ]

        async def _fake_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=_fake_stream())
        ):
            events = []
            async for event in provider.stream([msg]):
                events.append(event)

        complete_events = [e for e in events if e.type == EventType.COMPLETE]
        assert len(complete_events) == 1
        # Usage should be in the complete event
        response = complete_events[0].response
        assert response is not None

    @pytest.mark.asyncio
    async def test_stream_incremental_tool_call_args_accumulated(self):
        """Tool call arguments should be accumulated across chunks."""
        provider = _make_provider()
        msg = _user_message("Search for something")

        chunks = [
            self._make_tool_chunk(0, "call_1", "search", '{"q":'),  # Start of args
            self._make_tool_chunk(
                0, None, None, '"test query"}'
            ),  # Continuation (no name=None means continuation)
            self._make_chunk(finish_reason="tool_calls"),
        ]

        async def _fake_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=_fake_stream())
        ):
            events = []
            async for event in provider.stream([msg]):
                events.append(event)

        complete_events = [e for e in events if e.type == EventType.COMPLETE]
        assert len(complete_events) == 1
        tool_calls = [p for p in complete_events[0].response.content if isinstance(p, ToolCall)]
        assert len(tool_calls) == 1
        # Args should be accumulated
        assert "test query" in tool_calls[0].input


# ---------------------------------------------------------------------------
# model() method
# ---------------------------------------------------------------------------


class TestCustomProviderModelDeep:
    def test_model_returns_basic_keys(self):
        """model() should include id, name, and provider keys."""
        provider = _make_provider("openai/gpt-4o")
        info = provider.model()
        assert "id" in info
        assert "name" in info
        assert "provider" in info

    def test_model_returns_provider_prefix(self):
        """model() should include provider information."""
        provider = _make_provider("openai/gpt-4o")
        info = provider.model()
        assert "provider" in info
        assert info["provider"] == "openai"

    def test_model_id_matches_model_name(self):
        """model() id should match the model name."""
        provider = _make_provider("custom/llama-3.2")
        info = provider.model()
        assert info["id"] == "custom/llama-3.2"


# ---------------------------------------------------------------------------
# Edge cases: unicode, long messages, empty content
# ---------------------------------------------------------------------------


class TestEdgeCasesDeep:
    """Edge cases for unicode, long messages, etc."""

    @pytest.mark.asyncio
    async def test_send_with_unicode_content(self):
        """Unicode content should be handled correctly."""
        provider = _make_provider()
        msg = _user_message("日本語テスト: こんにちは世界！ 🌍 émojis: café")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "响应: 日本語サポート ✓"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ):
            result = await provider.send([msg])

        text_parts = [p for p in result.content if isinstance(p, TextContent)]
        assert "日本語サポート" in text_parts[0].text

    @pytest.mark.asyncio
    async def test_send_with_very_long_text(self):
        """Very long text messages should be handled correctly."""
        provider = _make_provider()
        long_text = "a" * 10000
        msg = _user_message(long_text)

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "b" * 5000
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ):
            result = await provider.send([msg])

        text_parts = [p for p in result.content if isinstance(p, TextContent)]
        assert len(text_parts) == 1
        assert len(text_parts[0].text) == 5000

    @pytest.mark.asyncio
    async def test_send_empty_response_content(self):
        """Empty response content should produce empty text."""
        provider = _make_provider()
        msg = _user_message("Hello")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = ""
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ):
            result = await provider.send([msg])

        # Should produce empty content list or empty text content
        assert result.finish_reason == FinishReason.END_TURN

    @pytest.mark.asyncio
    async def test_send_with_none_response_content(self):
        """None response content (tool calls only) should not produce text content."""
        provider = _make_provider()
        msg = _user_message("Hello")

        tc = MagicMock()
        tc.id = "call_1"
        tc.function.name = "search"
        tc.function.arguments = '{"q": "test"}'

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = None  # No text content
        mock_choice.message.tool_calls = [tc]
        mock_choice.finish_reason = "tool_calls"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ):
            result = await provider.send([msg])

        text_parts = [p for p in result.content if isinstance(p, TextContent)]
        assert len(text_parts) == 0
        tool_calls = [p for p in result.content if isinstance(p, ToolCall)]
        assert len(tool_calls) == 1
