"""
Unit tests for src/ii_agent/agent/runtime/models/openai/completions.py

Tests cover:
- _format_file_for_message utility
- OpenAIChat class defaults and instantiation
- OpenAIChat._get_client_params()
- OpenAIChat.get_request_params()
- OpenAIChat._format_message() – all role branches
- OpenAIChat._parse_provider_response() – text, tool calls, audio, reasoning, usage
- OpenAIChat._parse_provider_response_delta() – streaming events
- OpenAIChat.format_function_call_results()
- OpenAIChat ainvoke error handling
- OpenAIChat ainvoke happy path
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from ii_agent.agent.runtime.models.openai.completions import (
    OpenAIChat,
    _format_file_for_message,
)
from ii_agent.agent.runtime.models.message import Message
from ii_agent.agent.runtime.models.metrics import Metrics
from ii_agent.agent.runtime.models.response import ModelResponse
from ii_agent.agent.runtime.exceptions import (
    ModelAuthenticationError,
    ModelProviderError,
)
from ii_agent.agent.runtime.media.media import File


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_oai_chat(**kwargs) -> OpenAIChat:
    m = OpenAIChat(**kwargs)
    mock_async = MagicMock()
    mock_async.is_closed.return_value = False
    mock_async.chat = MagicMock()
    mock_async.chat.completions = MagicMock()
    m.async_client = mock_async

    mock_sync = MagicMock()
    mock_sync.is_closed.return_value = False
    m.client = mock_sync
    return m


def _make_usage(prompt=10, completion=20, total=30, reasoning=0):
    u = MagicMock()
    u.prompt_tokens = prompt
    u.completion_tokens = completion
    u.total_tokens = total
    # completion_tokens_details for reasoning_tokens
    u.completion_tokens_details = MagicMock()
    u.completion_tokens_details.audio_tokens = 0
    u.completion_tokens_details.reasoning_tokens = reasoning
    # prompt_tokens_details — set to None to avoid MagicMock arithmetic issues
    u.prompt_tokens_details = None
    u.cost = None
    return u


def _make_choice(finish_reason="stop", message_content="Hi", tool_calls=None,
                 reasoning_content=None, audio_output=None, role="assistant"):
    choice = MagicMock()
    choice.finish_reason = finish_reason
    msg = MagicMock()
    msg.role = role
    msg.content = message_content
    msg.tool_calls = tool_calls
    msg.reasoning_content = reasoning_content
    # reasoning is None by default to avoid double-setting
    msg.reasoning = None
    msg.audio = audio_output
    # parsed is None by default
    msg.parsed = None
    choice.message = msg
    return choice


def _make_completion(choices, usage=None, model="gpt-4o", completion_id="cmpl_123"):
    comp = MagicMock()
    comp.id = completion_id
    comp.model = model
    comp.choices = choices
    comp.usage = usage or _make_usage()
    # Explicitly set error to None to avoid MagicMock truthy check in _parse_provider_response
    comp.error = None
    comp.system_fingerprint = None
    comp.model_extra = None
    return comp


def _make_chunk(choices, usage=None):
    chunk = MagicMock()
    chunk.choices = choices
    chunk.usage = usage
    return chunk


def _make_chunk_choice(delta_content=None, delta_tool_calls=None, finish_reason=None,
                       delta_reasoning=None):
    choice = MagicMock()
    choice.finish_reason = finish_reason
    delta = MagicMock()
    delta.content = delta_content
    delta.tool_calls = delta_tool_calls
    delta.reasoning_content = delta_reasoning
    delta.audio = None
    choice.delta = delta
    return choice


# ---------------------------------------------------------------------------
# 1. _format_file_for_message
# ---------------------------------------------------------------------------

class TestFormatFileForMessage:
    def test_none_returns_none_for_external_only_file(self):
        # File requires at least one of url/filepath/content/external.
        # Using external={"ref": "external_file"} means url/filepath/content are None,
        # so _format_file_for_message falls through all cases and returns None.
        file = File(external={"ref": "external_file"})
        result = _format_file_for_message(file)
        assert result is None

    def test_file_with_bytes_content(self):
        content = b"%PDF-1.4 data"
        file = File(content=content, mime_type="application/pdf", filename="test.pdf")
        result = _format_file_for_message(file)
        assert result is not None
        assert result["type"] == "file"
        assert "file_data" in result["file"]

    def test_file_with_filepath(self, tmp_path):
        test_file = tmp_path / "document.txt"
        test_file.write_bytes(b"Hello PDF content")
        file = File(filepath=str(test_file), mime_type="text/plain")
        result = _format_file_for_message(file)
        assert result is not None
        assert result["type"] == "file"
        assert result["file"]["filename"] == "document.txt"

    def test_file_with_nonexistent_filepath_returns_none(self):
        file = File(filepath="/nonexistent/path.pdf")
        result = _format_file_for_message(file)
        assert result is None

    def test_data_url_format_contains_base64(self):
        content = b"pdf content"
        file = File(content=content, mime_type="application/pdf", filename="doc.pdf")
        result = _format_file_for_message(file)
        assert "data:application/pdf;base64," in result["file"]["file_data"]


# ---------------------------------------------------------------------------
# 2. OpenAIChat defaults
# ---------------------------------------------------------------------------

class TestOpenAIChatDefaults:
    def test_default_id(self):
        assert OpenAIChat().id == "gpt-4o"

    def test_default_name(self):
        assert OpenAIChat().name == "OpenAIChat"

    def test_default_provider_string(self):
        assert OpenAIChat().provider == "OpenAI"

    def test_default_supports_native_structured_outputs(self):
        assert OpenAIChat().supports_native_structured_outputs is True

    def test_default_strict_output_true(self):
        assert OpenAIChat().strict_output is True

    def test_default_temperature_none(self):
        assert OpenAIChat().temperature is None

    def test_default_max_tokens_none(self):
        assert OpenAIChat().max_tokens is None

    def test_custom_id(self):
        assert OpenAIChat(id="gpt-4-turbo").id == "gpt-4-turbo"

    def test_client_starts_none(self):
        assert OpenAIChat().client is None

    def test_async_client_starts_none(self):
        assert OpenAIChat().async_client is None

    def test_default_role_map_has_system(self):
        m = OpenAIChat()
        assert "system" in m.default_role_map
        assert m.default_role_map["system"] == "developer"

    def test_parallel_tool_calls_default_true(self):
        assert OpenAIChat().parallel_tool_calls is True


# ---------------------------------------------------------------------------
# 3. _get_client_params
# ---------------------------------------------------------------------------

class TestOpenAIChatGetClientParams:
    def test_api_key_included(self):
        m = OpenAIChat(api_key="sk-test")
        assert m._get_client_params()["api_key"] == "sk-test"

    def test_organization_included_when_set(self):
        m = OpenAIChat(api_key="key", organization="org_123")
        assert m._get_client_params()["organization"] == "org_123"

    def test_none_values_filtered(self):
        m = OpenAIChat(api_key="key", organization=None)
        assert "organization" not in m._get_client_params()

    @patch.dict("os.environ", {"OPENAI_API_KEY": "env_sk_key"}, clear=False)
    def test_api_key_from_env(self):
        m = OpenAIChat()
        m.api_key = None
        assert m._get_client_params()["api_key"] == "env_sk_key"

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_api_key_raises_auth_error(self):
        m = OpenAIChat()
        m.api_key = None
        with pytest.raises(ModelAuthenticationError):
            m._get_client_params()

    def test_timeout_included(self):
        m = OpenAIChat(api_key="key", timeout=60.0)
        assert m._get_client_params()["timeout"] == 60.0

    def test_base_url_included(self):
        m = OpenAIChat(api_key="key", base_url="https://custom.openai.com")
        assert m._get_client_params()["base_url"] == "https://custom.openai.com"

    def test_extra_client_params_merged(self):
        m = OpenAIChat(api_key="key", client_params={"custom_param": "val"})
        assert m._get_client_params()["custom_param"] == "val"


# ---------------------------------------------------------------------------
# 4. get_request_params
# ---------------------------------------------------------------------------

class TestOpenAIChatGetRequestParams:
    def test_temperature_included(self):
        m = _make_oai_chat(api_key="key", temperature=0.7)
        assert m.get_request_params()["temperature"] == 0.7

    def test_max_tokens_included(self):
        m = _make_oai_chat(api_key="key", max_tokens=2048)
        assert m.get_request_params()["max_tokens"] == 2048

    def test_seed_included(self):
        m = _make_oai_chat(api_key="key", seed=42)
        assert m.get_request_params()["seed"] == 42

    def test_stop_included(self):
        m = _make_oai_chat(api_key="key", stop=["STOP", "END"])
        assert m.get_request_params()["stop"] == ["STOP", "END"]

    def test_top_p_included(self):
        m = _make_oai_chat(api_key="key", top_p=0.9)
        assert m.get_request_params()["top_p"] == 0.9

    def test_frequency_penalty_included(self):
        m = _make_oai_chat(api_key="key", frequency_penalty=0.2)
        assert m.get_request_params()["frequency_penalty"] == 0.2

    def test_presence_penalty_included(self):
        m = _make_oai_chat(api_key="key", presence_penalty=0.1)
        assert m.get_request_params()["presence_penalty"] == 0.1

    def test_none_values_excluded(self):
        m = _make_oai_chat(api_key="key")
        params = m.get_request_params()
        assert "temperature" not in params
        assert "max_tokens" not in params

    def test_tools_included(self):
        m = _make_oai_chat(api_key="key")
        tools = [{"type": "function", "function": {"name": "search"}}]
        params = m.get_request_params(tools=tools)
        assert "tools" in params
        assert len(params["tools"]) == 1

    def test_tool_choice_included_with_tools(self):
        m = _make_oai_chat(api_key="key")
        tools = [{"type": "function", "function": {"name": "fn"}}]
        params = m.get_request_params(tools=tools, tool_choice="auto")
        assert params["tool_choice"] == "auto"

    def test_tool_choice_not_included_without_tools(self):
        m = _make_oai_chat(api_key="key")
        params = m.get_request_params(tools=None, tool_choice="auto")
        assert "tool_choice" not in params

    def test_request_params_merged(self):
        m = _make_oai_chat(api_key="key", request_params={"custom": "val"})
        assert m.get_request_params().get("custom") == "val"

    def test_reasoning_effort_included(self):
        m = _make_oai_chat(api_key="key", reasoning_effort="high")
        assert m.get_request_params().get("reasoning_effort") == "high"


# ---------------------------------------------------------------------------
# 5. _format_message
# ---------------------------------------------------------------------------

class TestOpenAIChatFormatMessage:
    def test_user_message_formatted(self):
        m = _make_oai_chat(api_key="key")
        msg = Message(role="user", content="Hello")
        result = m._format_message(msg)
        assert result["role"] == "user"
        assert result["content"] == "Hello"

    def test_system_message_mapped_to_developer(self):
        m = _make_oai_chat(api_key="key")
        msg = Message(role="system", content="System instruction")
        result = m._format_message(msg)
        assert result["role"] == "developer"

    def test_assistant_message_formatted(self):
        m = _make_oai_chat(api_key="key")
        msg = Message(role="assistant", content="Hello there")
        result = m._format_message(msg)
        assert result["role"] == "assistant"
        assert result["content"] == "Hello there"

    def test_assistant_null_content_becomes_empty_string(self):
        m = _make_oai_chat(api_key="key")
        msg = Message(role="assistant", content=None)
        result = m._format_message(msg)
        assert result["content"] == ""

    def test_tool_message_formatted(self):
        m = _make_oai_chat(api_key="key")
        msg = Message(role="tool", content="result", tool_call_id="tc_1")
        result = m._format_message(msg)
        assert result["role"] == "tool"
        assert result["tool_call_id"] == "tc_1"
        assert result["content"] == "result"

    def test_assistant_with_reasoning_content(self):
        m = _make_oai_chat(api_key="key")
        msg = Message(role="assistant", content="Answer", reasoning_content="My reasoning")
        result = m._format_message(msg)
        assert result["reasoning_content"] == "My reasoning"

    def test_empty_tool_calls_set_to_none(self):
        m = _make_oai_chat(api_key="key")
        msg = Message(role="assistant", content="Hi", tool_calls=[])
        result = m._format_message(msg)
        assert result.get("tool_calls") is None

    def test_tool_calls_included_when_non_empty(self):
        m = _make_oai_chat(api_key="key")
        tool_calls = [
            {"id": "tc_1", "type": "function", "function": {"name": "search", "arguments": "{}"}}
        ]
        msg = Message(role="assistant", content="", tool_calls=tool_calls)
        result = m._format_message(msg)
        assert result.get("tool_calls") is not None

    def test_message_with_files_appends_paths(self):
        from ii_agent.agent.runtime.models.message import File as MessageFile
        m = _make_oai_chat(api_key="key")
        file_obj = MessageFile(filepath=Path("/tmp/report.pdf"))
        msg = Message(role="user", content="See attached", files=[file_obj])
        result = m._format_message(msg)
        assert "Attached files" in result["content"]

    def test_message_with_images_adds_image_content(self):
        from ii_agent.agent.runtime.media import Image
        m = _make_oai_chat(api_key="key")
        img = Image(url="https://example.com/img.png", mime_type="image/png")
        msg = Message(role="user", content="Look!", images=[img])
        result = m._format_message(msg)
        assert isinstance(result["content"], list)

    def test_custom_role_map_used(self):
        m = _make_oai_chat(api_key="key", role_map={"user": "human", "assistant": "ai"})
        msg = Message(role="user", content="Hi")
        result = m._format_message(msg)
        assert result["role"] == "human"

    def test_audio_output_sets_audio_field(self):
        from ii_agent.agent.runtime.media.media import Audio
        m = _make_oai_chat(api_key="key")
        audio_output = Audio(id="audio_123", content=b"audio bytes")
        msg = Message(role="assistant", content="", audio_output=audio_output)
        result = m._format_message(msg)
        assert "audio" in result
        assert result["audio"]["id"] == "audio_123"


# ---------------------------------------------------------------------------
# 6. _parse_provider_response
# ---------------------------------------------------------------------------

class TestOpenAIChatParseProviderResponse:
    def test_role_set_to_assistant(self):
        m = _make_oai_chat(api_key="key")
        choice = _make_choice(message_content="Hello")
        mr = m._parse_provider_response(_make_completion([choice]))
        assert mr.role == "assistant"

    def test_text_content_extracted(self):
        m = _make_oai_chat(api_key="key")
        choice = _make_choice(message_content="Hello world")
        mr = m._parse_provider_response(_make_completion([choice]))
        assert mr.content == "Hello world"

    def test_tool_calls_extracted(self):
        m = _make_oai_chat(api_key="key")
        # model_dump() is called on tool calls in _parse_provider_response
        tc_dict = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "search", "arguments": '{"q": "test"}'},
        }
        tc = MagicMock()
        tc.model_dump.return_value = tc_dict
        choice = _make_choice(finish_reason="tool_calls", message_content=None, tool_calls=[tc])
        mr = m._parse_provider_response(_make_completion([choice]))
        assert len(mr.tool_calls) == 1
        assert mr.tool_calls[0]["function"]["name"] == "search"

    def test_tool_call_id_preserved(self):
        m = _make_oai_chat(api_key="key")
        tc_dict = {
            "id": "call_abc",
            "type": "function",
            "function": {"name": "fn", "arguments": "{}"},
        }
        tc = MagicMock()
        tc.model_dump.return_value = tc_dict
        choice = _make_choice(finish_reason="tool_calls", message_content=None, tool_calls=[tc])
        mr = m._parse_provider_response(_make_completion([choice]))
        assert mr.tool_calls[0]["id"] == "call_abc"

    def test_reasoning_content_extracted(self):
        m = _make_oai_chat(api_key="key")
        choice = _make_choice(message_content="Answer", reasoning_content="I reasoned")
        mr = m._parse_provider_response(_make_completion([choice]))
        assert mr.reasoning_content == "I reasoned"

    def test_usage_extracted(self):
        m = _make_oai_chat(api_key="key")
        choice = _make_choice(message_content="Hi")
        usage = _make_usage(prompt=15, completion=25, total=40)
        mr = m._parse_provider_response(_make_completion([choice], usage=usage))
        assert mr.response_usage is not None
        assert mr.response_usage.input_tokens == 15
        assert mr.response_usage.output_tokens == 25

    def test_reasoning_tokens_extracted(self):
        m = _make_oai_chat(api_key="key")
        choice = _make_choice(message_content="Hi")
        usage = _make_usage(reasoning=8)
        mr = m._parse_provider_response(_make_completion([choice], usage=usage))
        assert mr.response_usage.reasoning_tokens == 8

    def test_no_choices_raises_index_error(self):
        # When choices is empty, response.choices[0] raises IndexError.
        # This propagates uncaught from _parse_provider_response directly.
        m = _make_oai_chat(api_key="key")
        with pytest.raises(IndexError):
            m._parse_provider_response(_make_completion([]))

    def test_provider_data_response_id_stored(self):
        # The response.id is stored in model_response.provider_data["id"].
        m = _make_oai_chat(api_key="key")
        choice = _make_choice(message_content="ok")
        comp = _make_completion([choice], completion_id="cmpl_xyz")
        comp.id = "cmpl_xyz"
        mr = m._parse_provider_response(comp)
        assert mr.provider_data is not None
        assert mr.provider_data["id"] == "cmpl_xyz"


# ---------------------------------------------------------------------------
# 7. _parse_provider_response_delta (streaming)
# ---------------------------------------------------------------------------

class TestOpenAIChatParseProviderResponseDelta:
    def _stream_state(self):
        return {
            "current_type": None,
            "reasoning_started_emitted": False,
            "content_started_emitted": False,
            "reasoning_done_emitted": False,
            "content_done_emitted": False,
        }

    def test_text_delta_extracted(self):
        m = _make_oai_chat(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        chunk = _make_chunk([_make_chunk_choice(delta_content="Hello ")])
        result, _ = m._parse_provider_response_delta(chunk, assistant_msg, self._stream_state())
        assert result.content == "Hello "

    def test_reasoning_delta_extracted(self):
        m = _make_oai_chat(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        chunk = _make_chunk([_make_chunk_choice(delta_reasoning="I think ")])
        result, _ = m._parse_provider_response_delta(chunk, assistant_msg, self._stream_state())
        assert result.reasoning_content == "I think "

    def test_empty_chunk_returns_empty_response(self):
        m = _make_oai_chat(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        chunk = _make_chunk([])
        result, _ = m._parse_provider_response_delta(chunk, assistant_msg, self._stream_state())
        assert isinstance(result, ModelResponse)

    def test_tool_call_delta_extracted(self):
        m = _make_oai_chat(api_key="key")
        assistant_msg = Message(role="assistant", content="")

        tc_delta = MagicMock()
        tc_delta.index = 0
        tc_delta.id = "call_1"
        tc_delta.type = "function"
        tc_delta.function = MagicMock()
        tc_delta.function.name = "search"
        tc_delta.function.arguments = '{"q"'

        chunk = _make_chunk([_make_chunk_choice(delta_tool_calls=[tc_delta])])
        result, _ = m._parse_provider_response_delta(chunk, assistant_msg, self._stream_state())
        assert isinstance(result, ModelResponse)

    def test_usage_on_final_chunk(self):
        m = _make_oai_chat(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        usage = MagicMock()
        usage.prompt_tokens = 5
        usage.completion_tokens = 10
        usage.total_tokens = 15
        usage.completion_tokens_details = MagicMock(reasoning_tokens=0)
        chunk = _make_chunk([], usage=usage)
        result, _ = m._parse_provider_response_delta(chunk, assistant_msg, self._stream_state())
        assert result.response_usage is not None
        assert result.response_usage.input_tokens == 5

    def test_finish_reason_stop_is_handled(self):
        m = _make_oai_chat(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        state = self._stream_state()
        state["current_type"] = "content"
        state["content_started_emitted"] = True
        chunk = _make_chunk([_make_chunk_choice(finish_reason="stop")])
        result, new_state = m._parse_provider_response_delta(chunk, assistant_msg, state)
        assert isinstance(result, ModelResponse)


# ---------------------------------------------------------------------------
# 8. Tool message formatting (OpenAIChat uses _format_message for tool results)
# ---------------------------------------------------------------------------

class TestOpenAIChatToolMessageFormatting:
    def test_tool_message_formatted_with_tool_call_id(self):
        m = _make_oai_chat(api_key="key")
        msg = Message(role="tool", content="result_data", tool_call_id="call_123")
        result = m._format_message(msg)
        assert result["tool_call_id"] == "call_123"

    def test_tool_role_preserved_in_format_message(self):
        m = _make_oai_chat(api_key="key")
        msg = Message(role="tool", content="result", tool_call_id="tc_1")
        result = m._format_message(msg)
        assert result["role"] == "tool"

    def test_tool_message_content_in_result(self):
        m = _make_oai_chat(api_key="key")
        msg = Message(role="tool", content="computed answer", tool_call_id="tc_2")
        result = m._format_message(msg)
        assert result["content"] == "computed answer"

    def test_multiple_tool_results_all_have_tool_call_id(self):
        m = _make_oai_chat(api_key="key")
        msgs = [
            Message(role="tool", content="r1", tool_call_id="tc_1"),
            Message(role="tool", content="r2", tool_call_id="tc_2"),
        ]
        results = [m._format_message(msg) for msg in msgs]
        assert results[0]["tool_call_id"] == "tc_1"
        assert results[1]["tool_call_id"] == "tc_2"


# ---------------------------------------------------------------------------
# 9. ainvoke error handling
# ---------------------------------------------------------------------------

class TestOpenAIChatAinvokeErrors:
    @pytest.mark.asyncio
    async def test_rate_limit_error_raises_model_provider_error(self):
        from openai import RateLimitError
        m = _make_oai_chat(api_key="key")
        err = MagicMock(spec=RateLimitError)
        err.__class__ = RateLimitError
        err.response = MagicMock()
        err.response.json.return_value = {"error": {"message": "Rate limited"}}
        err.response.status_code = 429
        m.async_client.chat.completions.create = AsyncMock(side_effect=err)
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await m.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_api_connection_error_raises_model_provider_error(self):
        from openai import APIConnectionError
        m = _make_oai_chat(api_key="key")
        err = MagicMock(spec=APIConnectionError)
        err.__class__ = APIConnectionError
        err.args = ("connection failed",)
        m.async_client.chat.completions.create = AsyncMock(side_effect=err)
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await m.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_model_authentication_error_propagated(self):
        m = _make_oai_chat(api_key="key")
        m.async_client.chat.completions.create = AsyncMock(
            side_effect=ModelAuthenticationError("auth error", model_name="gpt-4o")
        )
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelAuthenticationError):
            await m.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_generic_exception_raises_model_provider_error(self):
        m = _make_oai_chat(api_key="key")
        m.async_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("unexpected")
        )
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await m.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_httpx_timeout_raises_model_provider_error(self):
        import httpx
        m = _make_oai_chat(api_key="key")
        m.async_client.chat.completions.create = AsyncMock(
            side_effect=httpx.TimeoutException("timed out")
        )
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await m.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_httpx_stream_error_raises_model_provider_error(self):
        import httpx
        m = _make_oai_chat(api_key="key")
        m.async_client.chat.completions.create = AsyncMock(
            side_effect=httpx.StreamError("stream broke")
        )
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await m.ainvoke(msgs, assistant)


# ---------------------------------------------------------------------------
# 10. ainvoke happy path
# ---------------------------------------------------------------------------

class TestOpenAIChatAinvokeHappyPath:
    @pytest.mark.asyncio
    async def test_ainvoke_returns_model_response(self):
        m = _make_oai_chat(api_key="test_key")
        choice = _make_choice(message_content="Hello from OpenAIChat!")
        comp = _make_completion([choice])
        m.async_client.chat.completions.create = AsyncMock(return_value=comp)

        msgs = [
            Message(role="system", content="Be helpful"),
            Message(role="user", content="Hi"),
        ]
        assistant = Message(role="assistant", content="")
        result = await m.ainvoke(msgs, assistant)
        assert isinstance(result, ModelResponse)
        assert result.role == "assistant"
        assert result.content == "Hello from OpenAIChat!"

    @pytest.mark.asyncio
    async def test_ainvoke_with_tool_call_response(self):
        m = _make_oai_chat(api_key="test_key")
        tc_dict = {
            "id": "call_search",
            "type": "function",
            "function": {"name": "search", "arguments": '{"q": "python"}'},
        }
        tc = MagicMock()
        tc.model_dump.return_value = tc_dict
        choice = _make_choice(finish_reason="tool_calls", message_content=None, tool_calls=[tc])
        comp = _make_completion([choice])
        m.async_client.chat.completions.create = AsyncMock(return_value=comp)

        msgs = [Message(role="user", content="Search for python")]
        assistant = Message(role="assistant", content="")
        result = await m.ainvoke(msgs, assistant)
        assert isinstance(result, ModelResponse)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["function"]["name"] == "search"

    @pytest.mark.asyncio
    async def test_ainvoke_with_json_content(self):
        # OpenAIChat._parse_provider_response does not handle the 'parsed' field;
        # structured output is just returned as string content.
        class AnswerSchema(BaseModel):
            answer: str

        m = _make_oai_chat(api_key="test_key")
        choice = MagicMock()
        choice.finish_reason = "stop"
        choice.message = MagicMock()
        choice.message.role = "assistant"
        choice.message.content = '{"answer": "42"}'
        choice.message.tool_calls = None
        choice.message.reasoning_content = None
        choice.message.reasoning = None
        choice.message.audio = None
        choice.message.parsed = None  # OpenAIChat doesn't use parsed
        comp = _make_completion([choice])
        m.async_client.chat.completions.create = AsyncMock(return_value=comp)

        msgs = [Message(role="user", content="What is the answer?")]
        assistant = Message(role="assistant", content="")
        result = await m.ainvoke(msgs, assistant, response_format=AnswerSchema)
        assert isinstance(result, ModelResponse)
        # OpenAIChat returns JSON as string content (no parsed field)
        assert result.content == '{"answer": "42"}'
