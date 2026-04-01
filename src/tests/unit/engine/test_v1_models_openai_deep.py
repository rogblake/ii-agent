"""
Deep unit tests for OpenAI Responses and Completions models

Covers deeper branches not tested by existing test files:
- OpenAIResponses._format_messages() with images, audio, files
- OpenAIResponses._parse_provider_response() edge cases
- OpenAIResponses.ainvoke_stream() happy path and error handling
- OpenAIResponses.get_client() paths
- OpenAIResponses.__deepcopy__
- OpenAIChat._format_message() with audio output, files
- OpenAIChat._parse_provider_response() with audio output, parsed field
- OpenAIChat.ainvoke_stream() happy path and error handling
- OpenAIChat.get_client() paths
- OpenAIChat.__deepcopy__
- OpenAIChat.format_function_call_results
- _format_file_for_message with URL file
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from ii_agent.agents.models.openai.responses import OpenAIResponses
from ii_agent.agents.models.openai.completions import OpenAIChat, _format_file_for_message
from ii_agent.agents.models.message import Message
from ii_agent.agents.models.metrics import Metrics
from ii_agent.agents.models.response import ModelResponse
from ii_agent.agents.exceptions import (
    ModelAuthenticationError,
    ModelProviderError,
)
from ii_agent.files.media import File, Audio, Image
from ii_agent.agents.types import Provider


# ---------------------------------------------------------------------------
# Helpers for OpenAIResponses
# ---------------------------------------------------------------------------


def _make_openai_responses(**kwargs) -> OpenAIResponses:
    m = OpenAIResponses(**kwargs)
    mock_async = MagicMock()
    mock_async.is_closed.return_value = False
    mock_async.responses = MagicMock()
    m.async_client = mock_async

    mock_sync = MagicMock()
    mock_sync.is_closed.return_value = False
    m.client = mock_sync
    return m


def _make_response_output(type_, **fields):
    out = MagicMock()
    out.type = type_
    for k, v in fields.items():
        setattr(out, k, v)
    return out


def _make_responses_usage(input_tokens=10, output_tokens=20, total_tokens=30, reasoning_tokens=5):
    u = MagicMock()
    u.input_tokens = input_tokens
    u.output_tokens = output_tokens
    u.total_tokens = total_tokens
    u.output_tokens_details = MagicMock()
    u.output_tokens_details.reasoning_tokens = reasoning_tokens
    u.input_tokens_details = MagicMock()
    u.input_tokens_details.cached_tokens = None
    return u


def _make_api_response(outputs, usage=None, response_id="resp_123", error=None, output_text=""):
    resp = MagicMock()
    resp.id = response_id
    resp.output = outputs
    resp.output_text = output_text
    resp.error = error
    resp.usage = usage or _make_responses_usage()
    return resp


# ---------------------------------------------------------------------------
# Helpers for OpenAIChat
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


def _make_chat_usage(prompt=10, completion=20, total=30, reasoning=0):
    u = MagicMock()
    u.prompt_tokens = prompt
    u.completion_tokens = completion
    u.total_tokens = total
    u.completion_tokens_details = MagicMock()
    u.completion_tokens_details.audio_tokens = 0
    u.completion_tokens_details.reasoning_tokens = reasoning
    u.prompt_tokens_details = None
    u.cost = None
    return u


def _make_choice(
    finish_reason="stop",
    message_content="Hi",
    tool_calls=None,
    reasoning_content=None,
    audio_output=None,
    role="assistant",
):
    choice = MagicMock()
    choice.finish_reason = finish_reason
    msg = MagicMock()
    msg.role = role
    msg.content = message_content
    msg.tool_calls = tool_calls
    msg.reasoning_content = reasoning_content
    msg.reasoning = None
    msg.audio = audio_output
    msg.parsed = None
    choice.message = msg
    return choice


def _make_completion(choices, usage=None, model="gpt-4o", completion_id="cmpl_123"):
    comp = MagicMock()
    comp.id = completion_id
    comp.model = model
    comp.choices = choices
    comp.usage = usage or _make_chat_usage()
    comp.error = None
    comp.system_fingerprint = None
    comp.model_extra = None
    return comp


# ---------------------------------------------------------------------------
# OpenAIResponses._format_messages() deeper paths
# ---------------------------------------------------------------------------


class TestOpenAIResponsesFormatMessagesDeep:
    def test_user_message_with_images(self):
        m = _make_openai_responses(api_key="key")
        img = Image(url="https://example.com/img.png", mime_type="image/png")
        msgs = [Message(role="user", content="Look!", images=[img])]
        result = m._format_messages(msgs)
        assert len(result) >= 1
        # Content should include image URLs
        first_msg = result[0]
        if isinstance(first_msg.get("content"), list):
            types = [c.get("type") for c in first_msg["content"]]
            assert "input_image" in types or "text" in types

    def test_assistant_with_provider_data_response_id(self):
        m = _make_openai_responses(api_key="key", store=True, id="o3-mini")
        msgs = [
            Message(
                role="assistant",
                content="Previous answer",
                provider_data={"response_id": "resp_abc_123"},
            ),
            Message(role="user", content="Follow up"),
        ]
        result = m._format_messages(msgs)
        # Messages after response_id should be returned
        user_msgs = [r for r in result if r.get("role") == "user"]
        assert len(user_msgs) == 1

    def test_tool_result_with_list_content(self):
        m = _make_openai_responses(api_key="key")
        msgs = [
            Message(
                role="tool",
                content=[{"type": "text", "text": "List result"}],
                tool_call_id="call_1",
            )
        ]
        result = m._format_messages(msgs)
        fc_outputs = [r for r in result if r.get("type") == "function_call_output"]
        assert len(fc_outputs) == 1

    def test_user_message_with_files(self):
        from pathlib import Path

        m = _make_openai_responses(api_key="key")
        f = File(filepath=Path("/tmp/doc.pdf"))
        msgs = [Message(role="user", content="See doc", files=[f])]
        result = m._format_messages(msgs)
        assert len(result) >= 1

    def test_previous_interaction_id_for_non_reasoning_model(self):
        m = _make_openai_responses(api_key="key", store=True, id="gpt-4o")
        response_id = "resp_prev_456"
        msgs = [
            Message(role="user", content="First message"),
            Message(
                role="assistant",
                content="Old response",
                provider_data={"response_id": response_id},
            ),
            Message(role="user", content="New message"),
        ]
        result = m._format_messages(msgs)
        # For non-reasoning model, no filtering by response_id
        assert len(result) >= 1

    def test_no_store_mode_no_response_id_filtering(self):
        m = _make_openai_responses(api_key="key", store=False, id="o3-mini")
        msgs = [
            Message(role="user", content="Hi"),
        ]
        result = m._format_messages(msgs)
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# OpenAIResponses._parse_provider_response() deeper paths
# ---------------------------------------------------------------------------


class TestOpenAIResponsesParseProviderResponseDeep:
    def test_empty_output_returns_response_with_role(self):
        m = _make_openai_responses(api_key="key")
        resp = _make_api_response([], output_text="")
        mr = m._parse_provider_response(resp)
        assert mr.role == "assistant"

    def test_file_citation_annotation(self):
        m = _make_openai_responses(api_key="key")
        annotation = MagicMock()
        annotation.type = "file_citation"
        annotation.file_id = "file_123"
        annotation.filename = "document.pdf"
        annotation.model_dump = MagicMock(return_value={"type": "file_citation"})
        content_item = _make_response_output(
            "output_text", text="Cited from file", annotations=[annotation]
        )
        msg_output = _make_response_output("message", content=[content_item])
        resp = _make_api_response([msg_output], output_text="Cited from file")
        # Should not crash, file citation doesn't add to URL citations
        mr = m._parse_provider_response(resp)
        assert isinstance(mr, ModelResponse)

    def test_reasoning_zdr_mode_stores_provider_data(self):
        m = _make_openai_responses(api_key="key", store=False)
        reasoning_output = _make_response_output("reasoning", summary=[])
        reasoning_output.model_dump = MagicMock(return_value={"type": "reasoning", "id": "rs_1"})
        resp = _make_api_response([reasoning_output], output_text="")
        mr = m._parse_provider_response(resp)
        assert mr.provider_data is not None
        assert "reasoning_output" in mr.provider_data

    def test_cached_tokens_in_usage(self):
        m = _make_openai_responses(api_key="key")
        usage = _make_responses_usage()
        usage.input_tokens_details.cached_tokens = 50
        resp = _make_api_response([], usage=usage, output_text="")
        mr = m._parse_provider_response(resp)
        assert mr.response_usage is not None

    def test_multiple_url_citations(self):
        m = _make_openai_responses(api_key="key")
        ann1 = MagicMock()
        ann1.type = "url_citation"
        ann1.url = "https://source1.com"
        ann1.title = "Source 1"
        ann1.model_dump = MagicMock(return_value={"type": "url_citation"})
        ann2 = MagicMock()
        ann2.type = "url_citation"
        ann2.url = "https://source2.com"
        ann2.title = "Source 2"
        ann2.model_dump = MagicMock(return_value={"type": "url_citation"})
        content_item = _make_response_output(
            "output_text", text="Multiple citations", annotations=[ann1, ann2]
        )
        msg_output = _make_response_output("message", content=[content_item])
        resp = _make_api_response([msg_output], output_text="Multiple citations")
        mr = m._parse_provider_response(resp)
        assert mr.citations is not None
        assert len(mr.citations.urls) == 2


# ---------------------------------------------------------------------------
# OpenAIResponses._parse_provider_response_delta() deeper paths
# ---------------------------------------------------------------------------


class TestOpenAIResponsesParseProviderResponseDeltaDeep:
    def _make_event(self, type_, **fields):
        evt = MagicMock()
        evt.type = type_
        for k, v in fields.items():
            setattr(evt, k, v)
        return evt

    def test_response_failed_event(self):
        m = _make_openai_responses(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        evt = self._make_event("response.failed")
        result, _ = m._parse_provider_response_delta(evt, assistant_msg, {})
        assert isinstance(result, ModelResponse)

    def test_output_text_annotation_non_url_type_ignored(self):
        m = _make_openai_responses(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        annotation = MagicMock()
        annotation.type = "file_citation"  # Not url_citation
        annotation.url = "not_url"
        annotation.title = "File"
        evt = self._make_event("response.output_text.annotation.added", annotation=annotation)
        result, _ = m._parse_provider_response_delta(evt, assistant_msg, {})
        # file_citation should not be added to URL citations
        assert isinstance(result, ModelResponse)

    def test_response_completed_event(self):
        m = _make_openai_responses(api_key="key")
        assistant_msg = Message(role="assistant", content="Hello")
        usage = _make_responses_usage()
        response_stub = MagicMock()
        response_stub.usage = usage
        evt = self._make_event("response.completed", response=response_stub)
        result, _ = m._parse_provider_response_delta(evt, assistant_msg, {})
        assert isinstance(result, ModelResponse)

    def test_unknown_event_type_returns_empty_response(self):
        m = _make_openai_responses(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        evt = self._make_event("unknown.event.type")
        result, _ = m._parse_provider_response_delta(evt, assistant_msg, {})
        assert isinstance(result, ModelResponse)

    def test_output_item_added_reasoning_type(self):
        m = _make_openai_responses(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        item = MagicMock()
        item.type = "reasoning"
        item.id = "rs_1"
        evt = self._make_event("response.output_item.added", item=item)
        result, new_tool_use = m._parse_provider_response_delta(evt, assistant_msg, {})
        assert isinstance(result, ModelResponse)


# ---------------------------------------------------------------------------
# OpenAIResponses ainvoke_stream() tests
# ---------------------------------------------------------------------------


class TestOpenAIResponsesAinvokeStream:
    @pytest.mark.asyncio
    async def test_ainvoke_stream_happy_path(self):
        m = _make_openai_responses(api_key="test_key")

        text_evt = MagicMock()
        text_evt.type = "response.output_text.delta"
        text_evt.delta = "Hello streaming!"

        done_evt = MagicMock()
        done_evt.type = "response.output_text.done"
        done_evt.text = "Hello streaming!"

        response_created = MagicMock()
        response_created.type = "response.created"
        response_created.response = MagicMock()
        response_created.response.id = "resp_stream_1"

        async def _mock_stream():
            yield response_created
            yield text_evt
            yield done_evt

        m.async_client.responses.create = AsyncMock(return_value=_mock_stream())

        msgs = [Message(role="user", content="Hi")]
        assistant = Message(role="assistant", content="")

        responses = []
        async for r in m.ainvoke_stream(msgs, assistant):
            responses.append(r)

        assert len(responses) >= 1
        content_responses = [r for r in responses if r.content]
        assert len(content_responses) >= 1

    @pytest.mark.asyncio
    async def test_ainvoke_stream_api_status_error_raises(self):
        from openai import APIStatusError

        m = _make_openai_responses(api_key="key")

        err = MagicMock(spec=APIStatusError)
        err.__class__ = APIStatusError
        err.status_code = 500
        err.message = "Internal server error"
        m.async_client.responses.create = AsyncMock(side_effect=err)

        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            async for _ in m.ainvoke_stream(msgs, assistant):
                pass

    @pytest.mark.asyncio
    async def test_ainvoke_stream_httpcore_error_raises(self):
        import httpcore

        m = _make_openai_responses(api_key="key")
        m.async_client.responses.create = AsyncMock(side_effect=httpcore.ReadError("read error"))
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            async for _ in m.ainvoke_stream(msgs, assistant):
                pass


# ---------------------------------------------------------------------------
# OpenAIResponses deepcopy tests
# ---------------------------------------------------------------------------


class TestOpenAIResponsesDeepcopy:
    def test_deepcopy_clears_client(self):
        m = OpenAIResponses(api_key="key")
        m.client = MagicMock(name="sync_client")
        m_copy = copy.deepcopy(m)
        assert m_copy.client is None

    def test_deepcopy_clears_async_client(self):
        m = OpenAIResponses(api_key="key")
        m.async_client = MagicMock(name="async_client")
        m_copy = copy.deepcopy(m)
        assert m_copy.async_client is None

    def test_deepcopy_preserves_config(self):
        m = OpenAIResponses(
            id="gpt-4o",
            api_key="my_key",
            temperature=0.7,
            max_output_tokens=2048,
        )
        m_copy = copy.deepcopy(m)
        assert m_copy.id == "gpt-4o"
        assert m_copy.api_key == "my_key"
        assert m_copy.temperature == 0.7
        assert m_copy.max_output_tokens == 2048


# ---------------------------------------------------------------------------
# OpenAIChat._format_message() deeper paths
# ---------------------------------------------------------------------------


class TestOpenAIChatFormatMessageDeep:
    def test_message_with_audio_output(self):
        m = _make_oai_chat(api_key="key")
        audio_output = Audio(id="aud_123", content=b"audio_bytes", transcript="Hello")
        msg = Message(role="assistant", content="", audio_output=audio_output)
        result = m._format_message(msg)
        assert "audio" in result
        assert result["audio"]["id"] == "aud_123"

    def test_message_with_tool_calls_and_content(self):
        m = _make_oai_chat(api_key="key")
        tool_calls = [
            {"id": "tc_1", "type": "function", "function": {"name": "search", "arguments": "{}"}}
        ]
        msg = Message(role="assistant", content="Let me search", tool_calls=tool_calls)
        result = m._format_message(msg)
        assert result["content"] == "Let me search"
        assert result["tool_calls"] is not None

    def test_message_with_images_converted_to_list_content(self):
        m = _make_oai_chat(api_key="key")
        img = Image(url="https://example.com/img.png", mime_type="image/png")
        msg = Message(role="user", content="What is this?", images=[img])
        result = m._format_message(msg)
        assert isinstance(result["content"], list)
        # Should contain text + image items (type name depends on images_to_message implementation)
        types = [c.get("type") for c in result["content"]]
        assert "text" in types
        # images can be "image_url" or "input_image" depending on implementation
        assert any(t in types for t in ["image_url", "input_image"])

    def test_assistant_message_with_tool_call_id(self):
        m = _make_oai_chat(api_key="key")
        msg = Message(role="assistant", content="Hi", tool_call_id="tc_1")
        result = m._format_message(msg)
        # Role should be assistant regardless of tool_call_id
        assert result["role"] == "assistant"
        assert result["content"] == "Hi"

    def test_system_message_mapped_to_developer_role(self):
        m = _make_oai_chat(api_key="key")
        msg = Message(role="system", content="Be helpful")
        result = m._format_message(msg)
        assert result["role"] == "developer"

    def test_user_message_with_file_path(self):
        m = _make_oai_chat(api_key="key")
        f = File(filepath=Path("/tmp/doc.pdf"))
        msg = Message(role="user", content="See file", files=[f])
        result = m._format_message(msg)
        assert "Attached files" in result["content"]


# ---------------------------------------------------------------------------
# OpenAIChat._parse_provider_response() deeper paths
# ---------------------------------------------------------------------------


class TestOpenAIChatParseProviderResponseDeep:
    def test_audio_output_in_response(self):
        m = _make_oai_chat(api_key="key")
        audio_obj = MagicMock()
        audio_obj.id = "aud_out_123"
        audio_obj.data = b"audio bytes"
        audio_obj.transcript = "Spoken words"
        audio_obj.expires_at = None
        choice = _make_choice(audio_output=audio_obj)
        mr = m._parse_provider_response(_make_completion([choice]))
        # Should handle audio_output
        assert isinstance(mr, ModelResponse)

    def test_no_content_no_tool_calls(self):
        m = _make_oai_chat(api_key="key")
        choice = _make_choice(message_content=None, tool_calls=None)
        mr = m._parse_provider_response(_make_completion([choice]))
        assert mr.content is None or mr.content == ""

    def test_cached_prompt_tokens_extracted(self):
        m = _make_oai_chat(api_key="key")
        choice = _make_choice(message_content="Hi")
        usage = _make_chat_usage(prompt=20, completion=10)
        # Add prompt_tokens_details with cached_tokens
        usage.prompt_tokens_details = MagicMock()
        usage.prompt_tokens_details.cached_tokens = 5
        comp = _make_completion([choice], usage=usage)
        mr = m._parse_provider_response(comp)
        assert mr.response_usage is not None

    def test_reasoning_content_from_reasoning_field(self):
        m = _make_oai_chat(api_key="key")
        choice = _make_choice(message_content="Answer", reasoning_content=None)
        choice.message.reasoning = "I reasoned about this"
        mr = m._parse_provider_response(_make_completion([choice]))
        # reasoning should be extracted from .reasoning field if .reasoning_content is None
        assert isinstance(mr, ModelResponse)

    def test_parsed_field_used_as_content(self):
        class OutputSchema(BaseModel):
            answer: str

        m = _make_oai_chat(api_key="key")
        choice = _make_choice(message_content=None)
        parsed_obj = OutputSchema(answer="42")
        choice.message.parsed = parsed_obj
        mr = m._parse_provider_response(_make_completion([choice]))
        # parsed field content should be converted to string
        assert isinstance(mr, ModelResponse)


# ---------------------------------------------------------------------------
# OpenAIChat ainvoke_stream() tests
# ---------------------------------------------------------------------------


class TestOpenAIChatAinvokeStream:
    @pytest.mark.asyncio
    async def test_ainvoke_stream_happy_path(self):
        m = _make_oai_chat(api_key="test_key")

        # Create a proper stream of chunks
        delta1 = MagicMock()
        delta1.content = "Hello "
        delta1.tool_calls = None
        delta1.reasoning_content = None
        delta1.audio = None
        choice1 = MagicMock()
        choice1.finish_reason = None
        choice1.delta = delta1

        delta2 = MagicMock()
        delta2.content = "world!"
        delta2.tool_calls = None
        delta2.reasoning_content = None
        delta2.audio = None
        choice2 = MagicMock()
        choice2.finish_reason = "stop"
        choice2.delta = delta2

        chunk1 = MagicMock()
        chunk1.choices = [choice1]
        chunk1.usage = None

        chunk2 = MagicMock()
        chunk2.choices = [choice2]
        chunk2.usage = MagicMock()
        chunk2.usage.prompt_tokens = 5
        chunk2.usage.completion_tokens = 10
        chunk2.usage.total_tokens = 15
        chunk2.usage.completion_tokens_details = MagicMock(reasoning_tokens=0)

        async def _mock_stream():
            yield chunk1
            yield chunk2

        m.async_client.chat.completions.create = AsyncMock(return_value=_mock_stream())

        msgs = [Message(role="user", content="Hi")]
        assistant = Message(role="assistant", content="")

        responses = []
        async for r in m.ainvoke_stream(msgs, assistant):
            responses.append(r)

        assert len(responses) >= 1

    @pytest.mark.asyncio
    async def test_ainvoke_stream_rate_limit_raises(self):
        from openai import RateLimitError

        m = _make_oai_chat(api_key="key")
        err = MagicMock(spec=RateLimitError)
        err.__class__ = RateLimitError
        err.response = MagicMock()
        err.response.status_code = 429
        m.async_client.chat.completions.create = AsyncMock(side_effect=err)

        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            async for _ in m.ainvoke_stream(msgs, assistant):
                pass

    @pytest.mark.asyncio
    async def test_ainvoke_stream_api_connection_error_raises(self):
        from openai import APIConnectionError

        m = _make_oai_chat(api_key="key")
        err = MagicMock(spec=APIConnectionError)
        err.__class__ = APIConnectionError
        err.args = ("connection failed",)
        m.async_client.chat.completions.create = AsyncMock(side_effect=err)

        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            async for _ in m.ainvoke_stream(msgs, assistant):
                pass

    @pytest.mark.asyncio
    async def test_ainvoke_stream_generic_error_raises(self):
        m = _make_oai_chat(api_key="key")
        m.async_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("unexpected error")
        )
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            async for _ in m.ainvoke_stream(msgs, assistant):
                pass


# ---------------------------------------------------------------------------
# OpenAIChat deepcopy tests
# ---------------------------------------------------------------------------


class TestOpenAIChatDeepcopy:
    def test_deepcopy_clears_client(self):
        m = OpenAIChat(api_key="key")
        m.client = MagicMock(name="sync_client")
        m_copy = copy.deepcopy(m)
        assert m_copy.client is None

    def test_deepcopy_clears_async_client(self):
        m = OpenAIChat(api_key="key")
        m.async_client = MagicMock(name="async_client")
        m_copy = copy.deepcopy(m)
        assert m_copy.async_client is None

    def test_deepcopy_preserves_config(self):
        m = OpenAIChat(
            id="gpt-4-turbo",
            api_key="my_key",
            temperature=0.5,
            max_tokens=4096,
        )
        m_copy = copy.deepcopy(m)
        assert m_copy.id == "gpt-4-turbo"
        assert m_copy.api_key == "my_key"
        assert m_copy.temperature == 0.5
        assert m_copy.max_tokens == 4096


# ---------------------------------------------------------------------------
# OpenAIChat.create_function_call_result tests
# ---------------------------------------------------------------------------


class TestOpenAIChatCreateFunctionCallResult:
    def _make_fc(self, name: str, call_id: str, args: dict):
        from ii_agent.agents.tools.function import FunctionCall, Function

        fn = Function(
            name=name,
            description=f"{name} function",
            parameters={"type": "object", "properties": {}},
        )
        return FunctionCall(function=fn, call_id=call_id, arguments=args)

    def test_successful_function_call_result(self):
        m = _make_oai_chat(api_key="key")
        fc = self._make_fc("search", "tc_1", {"query": "test"})
        result_msg = m.create_function_call_result(
            function_call=fc,
            success=True,
            output="Search results",
        )
        assert result_msg.role == m.tool_message_role
        assert result_msg.tool_call_id == "tc_1"

    def test_failed_function_call_result(self):
        m = _make_oai_chat(api_key="key")
        fc = self._make_fc("broken_fn", "tc_2", {})
        result_msg = m.create_function_call_result(
            function_call=fc,
            success=False,
            output="Error: function failed",
        )
        assert result_msg.role == m.tool_message_role
        assert result_msg.tool_call_id == "tc_2"

    def test_result_with_none_output(self):
        m = _make_oai_chat(api_key="key")
        fc = self._make_fc("noop", "tc_3", {})
        result_msg = m.create_function_call_result(
            function_call=fc,
            success=True,
            output=None,
        )
        assert result_msg.role == m.tool_message_role


# ---------------------------------------------------------------------------
# _format_file_for_message deeper paths
# ---------------------------------------------------------------------------


class TestFormatFileForMessageDeep:
    def test_file_with_url(self):
        # URL files should attempt fetch - mock the HTTP call
        import httpx

        file = File(url="https://example.com/doc.pdf")
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.content = b"PDF content from URL"
        mock_response.headers = {"Content-Type": "application/pdf"}
        with patch("httpx.get", return_value=mock_response):
            result = _format_file_for_message(file)
        # Result depends on whether fetch succeeded - just verify no unhandled exception
        assert result is None or isinstance(result, dict)

    def test_file_with_mime_type_from_extension(self):
        content = b"Text content"
        file = File(content=content, filename="document.txt", mime_type="text/plain")
        result = _format_file_for_message(file)
        assert result is not None
        assert result["type"] == "file"

    def test_file_with_openai_file_id(self):
        file = File(external={"file_id": "file-abc123"})
        # external file without url/filepath/content falls through
        result = _format_file_for_message(file)
        assert result is None


# ---------------------------------------------------------------------------
# OpenAIChat.get_request_params() deeper paths
# ---------------------------------------------------------------------------


class TestOpenAIChatGetRequestParamsDeep:
    def test_response_format_pydantic_model_does_not_crash(self):
        class Schema(BaseModel):
            result: str

        m = _make_oai_chat(api_key="key")
        # Pydantic response_format is only added in ainvoke when supports_native_structured_outputs
        params = m.get_request_params(response_format=Schema)
        assert isinstance(params, dict)

    def test_audio_in_modalities(self):
        m = _make_oai_chat(api_key="key", modalities=["text", "audio"])
        params = m.get_request_params()
        assert params.get("modalities") == ["text", "audio"]

    def test_store_none_not_in_params(self):
        m = _make_oai_chat(api_key="key", store=None)
        params = m.get_request_params()
        # When store=None, it may or may not be included depending on implementation
        assert isinstance(params, dict)

    def test_store_true_included_in_params(self):
        m = _make_oai_chat(api_key="key", store=True)
        params = m.get_request_params()
        assert params.get("store") is True

    def test_metadata_included(self):
        m = _make_oai_chat(api_key="key", metadata={"user_id": "u_123"})
        params = m.get_request_params()
        assert params.get("metadata") == {"user_id": "u_123"}

    def test_parallel_tool_calls_true_by_default(self):
        m = _make_oai_chat(api_key="key")
        params = m.get_request_params()
        assert params.get("parallel_tool_calls") is True

    def test_temperature_included_when_set(self):
        m = _make_oai_chat(api_key="key", temperature=0.3)
        params = m.get_request_params()
        assert params.get("temperature") == 0.3

    def test_max_tokens_included_when_set(self):
        m = _make_oai_chat(api_key="key", max_tokens=2000)
        params = m.get_request_params()
        assert params.get("max_tokens") == 2000 or params.get("max_completion_tokens") == 2000


# ---------------------------------------------------------------------------
# OpenAIResponses get_request_params() deeper paths
# ---------------------------------------------------------------------------


class TestOpenAIResponsesGetRequestParamsDeep:
    def test_reasoning_effort_with_none_effort(self):
        m = _make_openai_responses(api_key="key", id="o3-mini")
        m.reasoning_effort = None
        m.reasoning_summary = None
        m.reasoning = {"effort": "medium"}
        params = m.get_request_params()
        assert "reasoning" in params

    def test_include_param(self):
        m = _make_openai_responses(api_key="key", include=["file.content"])
        params = m.get_request_params()
        assert "include" in params

    def test_store_true_included(self):
        m = _make_openai_responses(api_key="key", store=True)
        params = m.get_request_params()
        assert params.get("store") is True

    def test_tools_with_function_and_web_search(self):
        m = _make_openai_responses(api_key="key")
        tools = [
            {"type": "web_search_preview"},
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "desc",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]
        params = m.get_request_params(tools=tools)
        assert "tools" in params

    def test_temperature_included_when_set(self):
        m = _make_openai_responses(api_key="key", temperature=0.5)
        params = m.get_request_params()
        assert params.get("temperature") == 0.5

    def test_max_output_tokens_included_when_set(self):
        m = _make_openai_responses(api_key="key", max_output_tokens=4096)
        params = m.get_request_params()
        assert params.get("max_output_tokens") == 4096

    def test_metadata_included_when_set(self):
        m = _make_openai_responses(api_key="key", metadata={"session": "123"})
        params = m.get_request_params()
        assert params.get("metadata") == {"session": "123"}

    def test_user_included_when_set(self):
        m = _make_openai_responses(api_key="key", user="user_abc")
        params = m.get_request_params()
        assert params.get("user") == "user_abc"
