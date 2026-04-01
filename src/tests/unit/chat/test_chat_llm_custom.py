"""Unit tests for chat/llm/custom.py - CustomProvider."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch, AsyncMock

import pytest

from ii_agent.chat.llm.custom import CustomProvider
from ii_agent.chat.types import (
    ArrayResultContent,
    BinaryContent,
    ErrorJsonContent,
    ErrorTextContent,
    EventType,
    ExecutionDeniedContent,
    FinishReason,
    ImageURLContent,
    JsonResultContent,
    Message,
    MessageRole,
    RunResponseEvent,
    StorybookProgressContent,
    StorybookResultContent,
    TextContent,
    TextResultContent,
    ToolCall,
    TextContentPart,
    ImageDataContentPart,
    FileDataContentPart,
    ImageUrlContentPart,
)
from ii_agent.settings.llm import Provider
from ii_agent.core.config.llm_config import LLMConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    model: str = "gpt-4",
    provider: Provider = Provider.CUSTOM,
    api_key: str | None = "sk-test",
    base_url: str | None = None,
    temperature: float = 0.0,
) -> LLMConfig:
    return LLMConfig(
        model=model,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    )


def _make_custom_provider(model="custom/gpt-4") -> CustomProvider:
    cfg = _make_config(model=model)
    return CustomProvider(cfg)


def _make_user_message(text: str) -> Message:
    msg = MagicMock(spec=Message)
    msg.role = MessageRole.USER
    msg.parts = [TextContent(text=text)]
    msg.tool_results = MagicMock(return_value=[])
    msg.tool_calls = MagicMock(return_value=[])
    return msg


def _make_assistant_message(text: str, tool_calls=None) -> Message:
    msg = MagicMock(spec=Message)
    msg.role = MessageRole.ASSISTANT
    msg.parts = [TextContent(text=text)]
    msg.tool_results = MagicMock(return_value=[])
    msg.tool_calls = MagicMock(return_value=tool_calls or [])
    return msg


def _make_tool_message(tool_results: list) -> Message:
    msg = MagicMock(spec=Message)
    msg.role = MessageRole.TOOL
    msg.parts = []
    msg.tool_results = MagicMock(return_value=tool_results)
    msg.tool_calls = MagicMock(return_value=[])
    return msg


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestCustomProviderInit:
    def test_model_name_set(self):
        provider = _make_custom_provider("custom/gpt-4")
        assert provider.model_name == "custom/gpt-4"

    def test_provider_prefix_extracted(self):
        provider = _make_custom_provider("openai/gpt-4")
        assert provider.provider_prefix == "openai"

    def test_provider_prefix_defaults_to_custom_when_no_slash(self):
        provider = _make_custom_provider("gpt-4-turbo")
        assert provider.provider_prefix == "custom"

    def test_gemini_api_type_prefixed(self):
        cfg = _make_config(model="gemini-pro", provider=Provider.GOOGLE)
        provider = CustomProvider(cfg)
        assert provider.model_name.startswith("gemini/")

    def test_api_key_extracted(self):
        provider = _make_custom_provider()
        assert provider.api_key == "sk-test"

    def test_api_key_none_when_not_set(self):
        cfg = _make_config(api_key=None)
        provider = CustomProvider(cfg)
        assert provider.api_key is None

    def test_base_url_set(self):
        cfg = _make_config(base_url="http://localhost:8080")
        provider = CustomProvider(cfg)
        assert provider.base_url == "http://localhost:8080"


# ---------------------------------------------------------------------------
# model() method
# ---------------------------------------------------------------------------


class TestCustomProviderModel:
    def test_model_returns_dict(self):
        provider = _make_custom_provider("custom/llama-3")
        info = provider.model()
        assert "id" in info
        assert "name" in info
        assert "provider" in info

    def test_model_returns_correct_name(self):
        provider = _make_custom_provider("custom/llama-3")
        info = provider.model()
        assert info["name"] == "custom/llama-3"


# ---------------------------------------------------------------------------
# _convert_tools
# ---------------------------------------------------------------------------


class TestConvertTools:
    def test_none_returns_none(self):
        provider = _make_custom_provider()
        assert provider._convert_tools(None) is None

    def test_empty_returns_none(self):
        provider = _make_custom_provider()
        assert provider._convert_tools([]) is None

    def test_tool_with_function_key_passed_through(self):
        provider = _make_custom_provider()
        tool = {"type": "function", "function": {"name": "x", "description": "y", "parameters": {}}}
        result = provider._convert_tools([tool])
        assert result == [tool]

    def test_tool_with_name_key_converted_to_function_format(self):
        provider = _make_custom_provider()
        tool = {"name": "search", "description": "Search", "parameters": {"type": "object"}}
        result = provider._convert_tools([tool])
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "search"

    def test_tool_without_function_or_name_passed_through(self):
        provider = _make_custom_provider()
        tool = {"custom_format": True}
        result = provider._convert_tools([tool])
        assert result == [tool]


# ---------------------------------------------------------------------------
# _convert_messages - tool role
# ---------------------------------------------------------------------------


class TestConvertMessagesTool:
    def test_text_result_content_converted_to_string(self):
        provider = _make_custom_provider()
        output = TextResultContent(value="the answer")
        tr = MagicMock()
        tr.tool_call_id = "call_1"
        tr.name = "search"
        tr.output = output
        msg = _make_tool_message([tr])

        converted = provider._convert_messages([msg])
        assert len(converted) == 1
        assert converted[0]["role"] == "tool"
        assert converted[0]["content"] == "the answer"

    def test_error_text_result_content(self):
        provider = _make_custom_provider()
        output = ErrorTextContent(value="error message")
        tr = MagicMock()
        tr.tool_call_id = "call_2"
        tr.name = "tool"
        tr.output = output
        msg = _make_tool_message([tr])

        converted = provider._convert_messages([msg])
        assert converted[0]["content"] == "error message"

    def test_json_result_content_serialized(self):
        provider = _make_custom_provider()
        output = JsonResultContent(value={"key": "val"})
        tr = MagicMock()
        tr.tool_call_id = "call_3"
        tr.name = "tool"
        tr.output = output
        msg = _make_tool_message([tr])

        converted = provider._convert_messages([msg])
        assert json.loads(converted[0]["content"]) == {"key": "val"}

    def test_execution_denied_content(self):
        provider = _make_custom_provider()
        output = ExecutionDeniedContent(reason="Not allowed")
        tr = MagicMock()
        tr.tool_call_id = "call_4"
        tr.name = "tool"
        tr.output = output
        msg = _make_tool_message([tr])

        converted = provider._convert_messages([msg])
        assert "Not allowed" in converted[0]["content"]

    def test_execution_denied_content_no_reason(self):
        provider = _make_custom_provider()
        output = ExecutionDeniedContent(reason=None)
        tr = MagicMock()
        tr.tool_call_id = "call_5"
        tr.name = "tool"
        tr.output = output
        msg = _make_tool_message([tr])

        converted = provider._convert_messages([msg])
        assert "denied" in converted[0]["content"].lower()

    def test_array_result_content_with_text_parts(self):
        provider = _make_custom_provider()
        text_item = TextContentPart(text="part text")
        output = ArrayResultContent(value=[text_item])
        tr = MagicMock()
        tr.tool_call_id = "call_6"
        tr.name = "tool"
        tr.output = output
        msg = _make_tool_message([tr])

        converted = provider._convert_messages([msg])
        assert "part text" in converted[0]["content"]

    def test_array_result_with_image_data_part(self):
        provider = _make_custom_provider()
        img_item = ImageDataContentPart(media_type="image/png", data="abc123")
        output = ArrayResultContent(value=[img_item])
        tr = MagicMock()
        tr.tool_call_id = "call_7"
        tr.name = "tool"
        tr.output = output
        msg = _make_tool_message([tr])

        converted = provider._convert_messages([msg])
        assert "image/png" in converted[0]["content"]

    def test_array_result_with_file_data_part(self):
        provider = _make_custom_provider()
        file_item = FileDataContentPart(
            data="base64data", mime_type="text/plain", filename="report.txt"
        )
        output = ArrayResultContent(value=[file_item])
        tr = MagicMock()
        tr.tool_call_id = "call_8"
        tr.name = "tool"
        tr.output = output
        msg = _make_tool_message([tr])

        converted = provider._convert_messages([msg])
        assert "report.txt" in converted[0]["content"]

    def test_fallback_unknown_type_uses_str(self):
        provider = _make_custom_provider()
        output = MagicMock()
        output.__class__.__name__ = "SomeUnknownOutput"
        # Make isinstance checks fail for all known types
        tr = MagicMock()
        tr.tool_call_id = "call_9"
        tr.name = "tool"
        tr.output = output
        msg = _make_tool_message([tr])

        converted = provider._convert_messages([msg])
        # Should not raise
        assert converted[0]["role"] == "tool"


# ---------------------------------------------------------------------------
# _convert_messages - non-tool roles
# ---------------------------------------------------------------------------


class TestConvertMessagesNonTool:
    def test_user_text_message(self):
        provider = _make_custom_provider()
        msg = _make_user_message("Hello!")
        converted = provider._convert_messages([msg])
        assert converted[0]["role"] == "user"
        assert converted[0]["content"] == "Hello!"

    def test_user_message_with_image_url(self):
        provider = _make_custom_provider()
        img = ImageURLContent(url="https://img.example.com/pic.jpg")
        msg = MagicMock(spec=Message)
        msg.role = MessageRole.USER
        msg.parts = [TextContent(text="Look at this"), img]
        msg.tool_results = MagicMock(return_value=[])
        msg.tool_calls = MagicMock(return_value=[])

        converted = provider._convert_messages([msg])
        content = converted[0]["content"]
        assert isinstance(content, list)

    def test_user_message_with_binary_content(self):
        provider = _make_custom_provider()
        binary = MagicMock(spec=BinaryContent)
        binary.to_base64 = MagicMock(return_value="data:image/png;base64,abc")
        msg = MagicMock(spec=Message)
        msg.role = MessageRole.USER
        msg.parts = [binary]
        msg.tool_results = MagicMock(return_value=[])
        msg.tool_calls = MagicMock(return_value=[])

        converted = provider._convert_messages([msg])
        content = converted[0]["content"]
        assert isinstance(content, list)

    def test_assistant_message_with_tool_calls(self):
        provider = _make_custom_provider()
        tc = MagicMock(spec=ToolCall)
        tc.id = "call_1"
        tc.name = "search"
        tc.input = '{"query": "python"}'
        msg = _make_assistant_message("Let me search", tool_calls=[tc])

        converted = provider._convert_messages([msg])
        assert "tool_calls" in converted[0]
        tc_data = converted[0]["tool_calls"][0]
        assert tc_data["id"] == "call_1"


# ---------------------------------------------------------------------------
# send()
# ---------------------------------------------------------------------------


class TestCustomProviderSend:
    @pytest.mark.asyncio
    async def test_send_prepends_system_message(self):
        provider = _make_custom_provider()
        msg = _make_user_message("Hello")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Hi there!"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ) as mock_acomp:
            result = await provider.send([msg])

        # Verify system message was added
        call_kwargs = mock_acomp.call_args
        messages_sent = call_kwargs[1]["messages"]
        assert messages_sent[0]["role"] == "system"

    @pytest.mark.asyncio
    async def test_send_returns_text_content(self):
        provider = _make_custom_provider()
        msg = _make_user_message("Hello")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Response text"
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
        assert text_parts[0].text == "Response text"

    @pytest.mark.asyncio
    async def test_send_returns_tool_calls(self):
        provider = _make_custom_provider()
        msg = _make_user_message("Search for x")

        tc_mock = MagicMock()
        tc_mock.id = "call_1"
        tc_mock.function.name = "search"
        tc_mock.function.arguments = '{"query": "x"}'

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = None
        mock_choice.message.tool_calls = [tc_mock]
        mock_choice.finish_reason = "tool_calls"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ):
            result = await provider.send([msg])

        tool_calls = [p for p in result.content if isinstance(p, ToolCall)]
        assert len(tool_calls) == 1
        assert result.finish_reason == FinishReason.TOOL_USE

    @pytest.mark.asyncio
    async def test_send_finish_reason_stop(self):
        provider = _make_custom_provider()
        msg = _make_user_message("Hello")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Done"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
        ):
            result = await provider.send([msg])

        assert result.finish_reason == FinishReason.END_TURN

    @pytest.mark.asyncio
    async def test_send_re_raises_exception(self):
        provider = _make_custom_provider()
        msg = _make_user_message("Hello")

        with patch(
            "ii_agent.chat.llm.custom.acompletion",
            new=AsyncMock(side_effect=RuntimeError("API error")),
        ):
            with pytest.raises(RuntimeError, match="API error"):
                await provider.send([msg])

    @pytest.mark.asyncio
    async def test_send_does_not_prepend_system_if_already_present(self):
        provider = _make_custom_provider()

        system_msg = MagicMock(spec=Message)
        system_msg.role = MessageRole.USER
        system_msg.parts = [TextContent(text="hello")]
        system_msg.tool_results = MagicMock(return_value=[])
        system_msg.tool_calls = MagicMock(return_value=[])

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "ok"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        # Pre-inject a system message by patching _convert_messages
        with patch.object(
            provider,
            "_convert_messages",
            return_value=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hello"},
            ],
        ):
            with patch(
                "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(return_value=mock_response)
            ) as mock_acomp:
                await provider.send([system_msg])

        call_kwargs = mock_acomp.call_args
        messages_sent = call_kwargs[1]["messages"]
        # Ensure system isn't added twice
        system_messages = [m for m in messages_sent if m["role"] == "system"]
        assert len(system_messages) == 1


# ---------------------------------------------------------------------------
# stream()
# ---------------------------------------------------------------------------


class TestCustomProviderStream:
    @pytest.mark.asyncio
    async def test_stream_emits_content_events(self):
        provider = _make_custom_provider()
        msg = _make_user_message("Hello")

        # Build streaming chunks
        def _make_chunk(content=None, finish_reason=None, tool_calls=None):
            chunk = MagicMock()
            delta = MagicMock()
            delta.content = content
            delta.tool_calls = tool_calls
            choice = MagicMock()
            choice.delta = delta
            choice.finish_reason = finish_reason
            chunk.choices = [choice]
            chunk.usage = None
            return chunk

        chunks = [
            _make_chunk(content="Hello"),
            _make_chunk(content=" world"),
            _make_chunk(finish_reason="stop"),
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
        assert EventType.CONTENT_START in event_types
        assert EventType.CONTENT_DELTA in event_types
        assert EventType.CONTENT_STOP in event_types
        assert EventType.COMPLETE in event_types

    @pytest.mark.asyncio
    async def test_stream_emits_tool_use_events(self):
        provider = _make_custom_provider()
        msg = _make_user_message("Search")

        def _make_tool_chunk(tc_index=0, tc_id="call_1", tc_name="search", args=None, finish=None):
            chunk = MagicMock()
            delta = MagicMock()
            delta.content = None
            tc_delta = MagicMock()
            tc_delta.index = tc_index
            tc_delta.id = tc_id
            tc_delta.function = MagicMock()
            tc_delta.function.name = tc_name
            tc_delta.function.arguments = args or ""
            delta.tool_calls = [tc_delta]
            choice = MagicMock()
            choice.delta = delta
            choice.finish_reason = finish
            chunk.choices = [choice]
            chunk.usage = None
            return chunk

        chunks = [
            _make_tool_chunk(tc_name="search", args='{"q":'),
            _make_tool_chunk(tc_name=None, args='"x"}'),
            _make_tool_chunk(finish="tool_calls"),
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

    @pytest.mark.asyncio
    async def test_stream_emits_error_event_on_exception(self):
        provider = _make_custom_provider()
        msg = _make_user_message("Hello")

        with patch(
            "ii_agent.chat.llm.custom.acompletion", new=AsyncMock(side_effect=RuntimeError("boom"))
        ):
            events = []
            async for event in provider.stream([msg]):
                events.append(event)

        assert any(e.type == EventType.ERROR for e in events)

    @pytest.mark.asyncio
    async def test_stream_finish_length_maps_to_max_tokens(self):
        provider = _make_custom_provider()
        msg = _make_user_message("Hello")

        def _make_chunk(content=None, finish_reason=None):
            chunk = MagicMock()
            delta = MagicMock()
            delta.content = content
            delta.tool_calls = None
            choice = MagicMock()
            choice.delta = delta
            choice.finish_reason = finish_reason
            chunk.choices = [choice]
            chunk.usage = None
            return chunk

        chunks = [
            _make_chunk(content="partial"),
            _make_chunk(finish_reason="length"),
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
        assert complete_events[0].response.finish_reason == FinishReason.MAX_TOKENS
