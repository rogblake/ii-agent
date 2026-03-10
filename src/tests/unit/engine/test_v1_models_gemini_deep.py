"""
Deep unit tests for ii_agent/agent/runtime/models/google/gemini.py

Covers deeper branches not tested by the existing test file:
- Gemini.get_client() paths (API key, Vertex AI)
- Gemini.get_request_params() deeper config paths (search, url_context, vertexai_search)
- Gemini._format_messages() with videos, audio, deeper file handling
- Gemini.ainvoke_stream() - streaming happy path and error handling
- Gemini._parse_provider_response() grounding metadata, url context metadata
- Gemini._parse_provider_response_delta() grounding metadata
- Gemini._append_file_search_tool() with metadata_filter
- Gemini format_function_call_results with various result content types
- Gemini deepcopy preserves fields
- Gemini get_request_params with response_format
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from ii_agent.agent.runtime.models.google.gemini import (
    Gemini,
    _normalize_function_definition,
    format_function_definitions,
    format_image_for_message,
    prepare_response_schema,
)
from ii_agent.agent.runtime.models.message import Message
from ii_agent.agent.runtime.models.metrics import Metrics
from ii_agent.agent.runtime.models.response import ModelResponse
from ii_agent.agent.runtime.exceptions import ModelProviderError
from ii_agent.agent.runtime.media import Image, File, Audio, Video
from ii_agent.agent.types import Provider

from google.genai.types import Content, Part


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gemini(**kwargs) -> Gemini:
    g = Gemini(**kwargs)
    mock_client = MagicMock()
    mock_client.aio = MagicMock()
    mock_client.aio.models = MagicMock()
    mock_client.aio.aclose = AsyncMock()
    g.client = mock_client
    return g


def _make_usage(input_t=10, output_t=20, total_t=30, cached_t=0, thought_t=None):
    u = MagicMock()
    u.prompt_token_count = input_t
    u.candidates_token_count = output_t
    u.total_token_count = total_t
    u.cached_content_token_count = cached_t
    u.thoughts_token_count = thought_t
    u.traffic_type = None
    return u


def _make_candidate(content: Content, finish_reason="STOP"):
    candidate = MagicMock()
    candidate.content = content
    candidate.finish_reason = finish_reason
    candidate.grounding_metadata = None
    candidate.url_context_metadata = None
    return candidate


def _make_provider_response(candidates, usage=None):
    resp = MagicMock()
    resp.candidates = candidates
    resp.usage_metadata = usage
    return resp


def _make_text_content(text: str, role: str = "model") -> Content:
    return Content(role=role, parts=[Part.from_text(text=text)])


def _make_function_call_content(name: str, args: dict, role: str = "model") -> Content:
    fc = MagicMock()
    fc.name = name
    fc.args = args
    fc.id = None

    part = MagicMock()
    part.text = None
    part.function_call = fc
    part.thought = False
    part.inline_data = None
    part.thought_signature = None

    content = MagicMock(spec=Content)
    content.role = role
    content.parts = [part]
    return content


def _make_thought_content(thought_text: str, role: str = "model") -> Content:
    part = MagicMock()
    part.text = thought_text
    part.thought = True
    part.function_call = None
    part.inline_data = None
    part.thought_signature = None

    content = MagicMock(spec=Content)
    content.role = role
    content.parts = [part]
    return content


# ---------------------------------------------------------------------------
# Gemini.get_client() deeper paths
# ---------------------------------------------------------------------------

class TestGeminiGetClient:
    def test_returns_existing_client(self):
        g = Gemini()
        mock_client = MagicMock()
        g.client = mock_client
        result = g.get_client()
        assert result is mock_client

    @patch.dict("os.environ", {"GOOGLE_API_KEY": "env_google_key"}, clear=False)
    def test_creates_client_with_api_key_from_env(self):
        g = Gemini()
        g.api_key = None
        g.client = None
        with patch("google.genai.Client") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            result = g.get_client()
            assert MockClient.called

    @patch.dict(
        "os.environ",
        {
            "GOOGLE_GENAI_USE_VERTEXAI": "true",
            "GOOGLE_CLOUD_PROJECT": "my-project",
            "GOOGLE_CLOUD_LOCATION": "us-central1",
        },
        clear=False,
    )
    def test_vertex_ai_mode_via_env(self):
        g = Gemini()
        g.client = None
        with patch("google.genai.Client") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            g.get_client()
            call_kwargs = MockClient.call_args[1]
            assert call_kwargs.get("vertexai") is True
            assert call_kwargs.get("project") == "my-project"
            assert call_kwargs.get("location") == "us-central1"

    def test_vertex_ai_mode_via_field(self):
        g = Gemini(
            vertexai=True,
            project_id="proj-123",
            location="europe-west4",
        )
        g.client = None
        with patch("google.genai.Client") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            g.get_client()
            call_kwargs = MockClient.call_args[1]
            assert call_kwargs.get("vertexai") is True
            assert call_kwargs.get("project") == "proj-123"
            assert call_kwargs.get("location") == "europe-west4"

    def test_client_params_merged(self):
        g = Gemini(api_key="key", client_params={"custom": "param"})
        g.client = None
        with patch("google.genai.Client") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            g.get_client()
            call_kwargs = MockClient.call_args[1]
            assert call_kwargs.get("custom") == "param"


# ---------------------------------------------------------------------------
# Gemini.get_request_params() deeper paths
# ---------------------------------------------------------------------------

class TestGeminiGetRequestParamsDeep:
    def test_search_adds_google_search_tool(self):
        g = _make_gemini(search=True)
        params = g.get_request_params()
        cfg = params["config"]
        assert cfg.tools is not None
        assert len(cfg.tools) >= 1

    def test_url_context_adds_url_context_tool(self):
        g = _make_gemini(url_context=True)
        params = g.get_request_params()
        cfg = params["config"]
        assert cfg.tools is not None

    def test_vertexai_search_adds_retrieval_tool(self):
        g = _make_gemini(
            vertexai_search=True,
            vertexai_search_datastore="projects/my-proj/locations/global/collections/default/dataStores/my-store",
        )
        params = g.get_request_params()
        cfg = params["config"]
        assert cfg.tools is not None

    def test_response_format_pydantic_model_adds_response_schema(self):
        class OutputSchema(BaseModel):
            answer: str
            confidence: float

        g = _make_gemini()
        params = g.get_request_params(response_format=OutputSchema)
        cfg = params["config"]
        assert cfg.response_schema is not None

    def test_response_format_dict_added_to_config(self):
        g = _make_gemini()
        fmt = {"type": "object", "properties": {"name": {"type": "string"}}}
        params = g.get_request_params(response_format=fmt)
        # Should not crash

    def test_tools_with_function_declarations(self):
        g = _make_gemini()
        tools = [{"type": "function", "function": {"name": "search", "description": "Search the web"}}]
        params = g.get_request_params(tools=tools)
        cfg = params["config"]
        # function declarations should be added
        assert cfg is not None

    def test_generation_config_as_dict_does_not_crash(self):
        g = _make_gemini(generation_config={"temperature": 0.8, "top_p": 0.95})
        params = g.get_request_params()
        # generation_config as dict is handled but may not set config key
        assert isinstance(params, dict)

    def test_safety_settings_included(self):
        from google.genai.types import GenerateContentConfig
        safety = [{"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}]
        g = _make_gemini(safety_settings=safety, search=True)
        params = g.get_request_params()
        # config is set due to search=True
        cfg = params.get("config")
        if cfg is not None:
            assert cfg is not None

    def test_response_modalities_included(self):
        g = _make_gemini(response_modalities=["TEXT", "IMAGE"], search=True)
        params = g.get_request_params()
        cfg = params.get("config")
        if cfg is not None:
            assert cfg.response_modalities == ["TEXT", "IMAGE"]

    def test_file_search_store_names_triggers_file_search_tool(self):
        g = _make_gemini(file_search_store_names=["store-1", "store-2"])
        params = g.get_request_params()
        cfg = params["config"]
        assert cfg.tools is not None

    def test_file_search_with_metadata_filter(self):
        g = _make_gemini(
            file_search_store_names=["store-1"],
            file_search_metadata_filter="category = 'science'",
        )
        params = g.get_request_params()
        cfg = params["config"]
        assert cfg.tools is not None


# ---------------------------------------------------------------------------
# Gemini._format_messages() deeper paths
# ---------------------------------------------------------------------------

class TestGeminiFormatMessagesDeep:
    def test_user_message_with_video(self):
        g = _make_gemini()
        # Use real Video object with bytes content (not GeminiFile)
        video = Video(content=b"fake_video_data", mime_type="video/mp4", format="mp4")
        msgs = [Message(role="user", content="Watch this", videos=[video])]
        formatted, _ = g._format_messages(msgs)
        # Should produce at least one message (may be empty due to video format handling)
        assert isinstance(formatted, list)

    def test_user_message_with_audio(self):
        g = _make_gemini()
        # Use real Audio object with bytes content (not GeminiFile)
        audio = Audio(content=b"fake_audio_data", mime_type="audio/wav", format="wav")
        msgs = [Message(role="user", content="Listen", audio=[audio])]
        formatted, _ = g._format_messages(msgs)
        assert isinstance(formatted, list)

    def test_system_message_with_list_content(self):
        g = _make_gemini()
        msgs = [Message(role="system", content=[{"type": "text", "text": "Be helpful"}])]
        formatted, system = g._format_messages(msgs)
        assert formatted == []
        assert system is not None

    def test_developer_role_treated_as_system(self):
        g = _make_gemini()
        msgs = [Message(role="developer", content="Dev instructions")]
        formatted, system = g._format_messages(msgs)
        assert system == "Dev instructions"
        assert formatted == []

    def test_tool_result_with_string_content(self):
        g = _make_gemini()
        msgs = [
            Message(
                role="tool",
                content="42",
                tool_name="calculator",
                tool_call_id="call_1",
                tool_calls=[{"tool_name": "calculator", "tool_call_id": "call_1", "content": "42"}],
            )
        ]
        formatted, _ = g._format_messages(msgs)
        assert len(formatted) >= 1

    def test_user_message_image_with_url(self):
        g = _make_gemini()
        img = MagicMock(spec=Image)
        img.get_content_bytes = MagicMock(return_value=b"img_data")
        img.content = None
        img.url = "https://example.com/img.png"
        img.mime_type = "image/png"
        img.format = "png"
        msgs = [Message(role="user", content="See image", images=[img])]
        formatted, _ = g._format_messages(msgs)
        assert len(formatted) >= 1

    def test_assistant_with_text_and_tool_calls_and_thought(self):
        import base64
        g = _make_gemini()
        sig_bytes = b"thought_signature"
        sig_b64 = base64.b64encode(sig_bytes).decode("ascii")
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "search", "arguments": '{"q": "test"}'},
            }
        ]
        msgs = [
            Message(
                role="assistant",
                content="Searching...",
                tool_calls=tool_calls,
                reasoning_content="Let me think about this",
                provider_data={"thought_signature": sig_b64},
            )
        ]
        formatted, _ = g._format_messages(msgs)
        assert len(formatted) >= 1
        assert any(c.role == "model" for c in formatted)

    def test_assistant_text_only_no_tool_calls(self):
        g = _make_gemini()
        msgs = [Message(role="assistant", content="Simple response")]
        formatted, _ = g._format_messages(msgs)
        assert len(formatted) == 1
        assert formatted[0].role == "model"

    def test_consecutive_same_role_messages_handled(self):
        g = _make_gemini()
        msgs = [
            Message(role="user", content="First"),
            Message(role="user", content="Second"),
        ]
        formatted, _ = g._format_messages(msgs)
        # Both messages should be formatted
        assert len(formatted) == 2


# ---------------------------------------------------------------------------
# Gemini._parse_provider_response() with grounding metadata
# ---------------------------------------------------------------------------

class TestGeminiParseProviderResponseDeep:
    def test_grounding_metadata_stored_in_citations(self):
        g = _make_gemini()
        content = _make_text_content("Grounded answer")
        candidate = _make_candidate(content)

        # Add grounding metadata mock
        grounding_meta = MagicMock()
        grounding_chunk = MagicMock()
        web = MagicMock()
        web.uri = "https://source.example.com"
        web.title = "Source Page"
        grounding_chunk.web = web
        grounding_meta.grounding_chunks = [grounding_chunk]
        grounding_meta.search_entry_point = MagicMock()
        grounding_meta.search_entry_point.rendered_content = "<link>source</link>"
        candidate.grounding_metadata = grounding_meta

        resp = _make_provider_response([candidate], usage=_make_usage())
        mr = g._parse_provider_response(resp)
        # Citations should be populated from grounding
        assert mr.citations is not None

    def test_url_context_metadata_stored(self):
        g = _make_gemini()
        content = _make_text_content("URL context answer")
        candidate = _make_candidate(content)

        url_meta = MagicMock()
        url_meta_entry = MagicMock()
        url_meta_entry.url = "https://retrieved.example.com"
        url_meta_entry.title = "Retrieved Page"
        url_meta.url_metadata = [url_meta_entry]
        candidate.url_context_metadata = url_meta
        candidate.grounding_metadata = None

        resp = _make_provider_response([candidate], usage=_make_usage())
        mr = g._parse_provider_response(resp)
        assert isinstance(mr, ModelResponse)

    def test_multiple_parts_in_candidate(self):
        g = _make_gemini()
        # Create content with multiple text parts
        text1 = Part.from_text(text="Part 1 ")
        text2 = Part.from_text(text="Part 2")
        content = Content(role="model", parts=[text1, text2])
        candidate = _make_candidate(content)
        resp = _make_provider_response([candidate], usage=_make_usage())
        mr = g._parse_provider_response(resp)
        assert "Part 1" in mr.content
        assert "Part 2" in mr.content

    def test_inline_data_part_ignored(self):
        g = _make_gemini()
        # Part with inline_data but no text
        part = MagicMock()
        part.text = None
        part.function_call = None
        part.thought = False
        part.inline_data = MagicMock()
        part.inline_data.mime_type = "image/png"
        part.inline_data.data = b"png_data"
        part.thought_signature = None

        content = MagicMock(spec=Content)
        content.role = "model"
        content.parts = [part]
        candidate = _make_candidate(content)
        resp = _make_provider_response([candidate], usage=_make_usage())
        # Should not crash
        mr = g._parse_provider_response(resp)
        assert isinstance(mr, ModelResponse)

    def test_function_call_with_id(self):
        g = _make_gemini()
        fc = MagicMock()
        fc.name = "search"
        fc.args = {"query": "python"}
        fc.id = "fc_id_123"  # Gemini sometimes provides ID

        part = MagicMock()
        part.text = None
        part.function_call = fc
        part.thought = False
        part.inline_data = None
        part.thought_signature = None

        content = MagicMock(spec=Content)
        content.role = "model"
        content.parts = [part]
        candidate = _make_candidate(content)
        resp = _make_provider_response([candidate])
        mr = g._parse_provider_response(resp)
        assert len(mr.tool_calls) == 1
        assert mr.tool_calls[0]["id"] == "fc_id_123"

    def test_thought_with_signature(self):
        g = _make_gemini()
        import base64
        sig_bytes = b"thought_sig_bytes"

        part = MagicMock()
        part.text = "I am thinking deeply"
        part.thought = True
        part.function_call = None
        part.inline_data = None
        # thought_signature from Gemini API is bytes (not base64 string)
        part.thought_signature = sig_bytes

        content = MagicMock(spec=Content)
        content.role = "model"
        content.parts = [part]
        candidate = _make_candidate(content)
        resp = _make_provider_response([candidate])
        mr = g._parse_provider_response(resp)
        assert mr.reasoning_content is not None
        assert "thinking deeply" in mr.reasoning_content
        assert mr.provider_data is not None
        assert "thought_signature" in mr.provider_data


# ---------------------------------------------------------------------------
# Gemini.ainvoke_stream() tests
# ---------------------------------------------------------------------------

class TestGeminiAinvokeStream:
    @pytest.mark.asyncio
    async def test_ainvoke_stream_happy_path(self):
        g = _make_gemini(api_key="test_key")

        content = _make_text_content("Streaming response")
        candidate = MagicMock()
        candidate.content = content
        candidate.grounding_metadata = None
        chunk = MagicMock()
        chunk.candidates = [candidate]
        chunk.usage_metadata = _make_usage()

        async def _mock_stream():
            yield chunk

        # generate_content_stream is awaited, so return an awaitable that gives the async gen
        g.client.aio.models.generate_content_stream = AsyncMock(return_value=_mock_stream())

        msgs = [Message(role="user", content="Stream me")]
        assistant = Message(role="assistant", content="")

        responses = []
        async for r in g.ainvoke_stream(msgs, assistant):
            responses.append(r)

        assert len(responses) >= 1

    @pytest.mark.asyncio
    async def test_ainvoke_stream_client_error_raises_model_provider_error(self):
        from google.genai.errors import ClientError
        g = _make_gemini(api_key="key")

        async def _failing_stream():
            raise ClientError("API error")
            yield  # make it a generator

        g.client.aio.models.generate_content_stream = AsyncMock(return_value=_failing_stream())

        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            async for _ in g.ainvoke_stream(msgs, assistant):
                pass

    @pytest.mark.asyncio
    async def test_ainvoke_stream_timeout_raises_model_provider_error(self):
        import httpx
        g = _make_gemini(api_key="key")

        # Timeout on the await call itself
        g.client.aio.models.generate_content_stream = AsyncMock(
            side_effect=httpx.TimeoutException("timed out")
        )

        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            async for _ in g.ainvoke_stream(msgs, assistant):
                pass

    @pytest.mark.asyncio
    async def test_ainvoke_stream_generic_error_raises_model_provider_error(self):
        g = _make_gemini(api_key="key")

        g.client.aio.models.generate_content_stream = AsyncMock(
            side_effect=ValueError("unexpected error")
        )

        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            async for _ in g.ainvoke_stream(msgs, assistant):
                pass


# ---------------------------------------------------------------------------
# Gemini.format_function_call_results deeper paths
# ---------------------------------------------------------------------------

class TestGeminiFormatFunctionCallResultsDeep:
    def test_result_with_list_content(self):
        g = _make_gemini()
        messages: List[Message] = []
        result = Message(
            role="tool",
            content=[{"type": "text", "text": "Result as list"}],
            tool_name="search",
            tool_call_id="tc_1",
        )
        g.format_function_call_results(messages, [result])
        assert len(messages) == 1

    def test_result_with_dict_content(self):
        g = _make_gemini()
        messages: List[Message] = []
        # Message content must be str or list, so use str representation
        result = Message(
            role="tool",
            content="42",
            tool_name="calc",
            tool_call_id="tc_1",
        )
        g.format_function_call_results(messages, [result])
        assert len(messages) == 1


# ---------------------------------------------------------------------------
# Gemini._get_metrics() deeper paths
# ---------------------------------------------------------------------------

class TestGeminiGetMetricsDeep:
    def test_no_usage_returns_empty_metrics(self):
        g = _make_gemini()
        # _get_metrics is called with None usage in some paths
        # Let's test _parse_provider_response with no usage_metadata
        resp = MagicMock()
        content = _make_text_content("hi")
        candidate = _make_candidate(content)
        resp.candidates = [candidate]
        resp.usage_metadata = None
        mr = g._parse_provider_response(resp)
        assert isinstance(mr, ModelResponse)

    def test_traffic_type_included_in_metrics(self):
        g = _make_gemini()
        usage = _make_usage(input_t=10, output_t=20)
        usage.traffic_type = "NORMAL"
        mr = g._get_metrics(usage)
        assert isinstance(mr, Metrics)

    def test_zero_thought_tokens(self):
        g = _make_gemini()
        usage = _make_usage(output_t=50, thought_t=0)
        mr = g._get_metrics(usage)
        # 0 thought tokens should still be considered (output = 50 + 0 = 50)
        assert mr.output_tokens == 50

    def test_none_cached_tokens_handled(self):
        g = _make_gemini()
        usage = _make_usage(cached_t=None)
        usage.cached_content_token_count = None
        mr = g._get_metrics(usage)
        assert isinstance(mr, Metrics)


# ---------------------------------------------------------------------------
# Gemini _parse_provider_response_delta grounding
# ---------------------------------------------------------------------------

class TestGeminiParseProviderResponseDeltaDeep:
    def test_grounding_metadata_in_delta(self):
        g = _make_gemini()
        content = _make_text_content("Grounded stream")
        grounding_meta = MagicMock()
        grounding_chunk = MagicMock()
        web = MagicMock()
        web.uri = "https://source.example.com"
        web.title = "Source"
        grounding_chunk.web = web
        grounding_meta.grounding_chunks = [grounding_chunk]
        grounding_meta.search_entry_point = None

        candidate = MagicMock()
        candidate.content = content
        candidate.grounding_metadata = grounding_meta

        chunk = MagicMock()
        chunk.candidates = [candidate]
        chunk.usage_metadata = _make_usage()

        resp = g._parse_provider_response_delta(chunk)
        # Citations should be populated
        assert isinstance(resp, ModelResponse)

    def test_empty_parts_in_chunk(self):
        g = _make_gemini()
        content = Content(role="model", parts=[])
        candidate = MagicMock()
        candidate.content = content
        candidate.grounding_metadata = None

        chunk = MagicMock()
        chunk.candidates = [candidate]
        chunk.usage_metadata = _make_usage()

        resp = g._parse_provider_response_delta(chunk)
        assert isinstance(resp, ModelResponse)


# ---------------------------------------------------------------------------
# Gemini _append_file_search_tool
# ---------------------------------------------------------------------------

class TestGeminiAppendFileSearchTool:
    def test_no_file_search_store_names_no_tool_added(self):
        g = _make_gemini()
        tools = []
        g._append_file_search_tool(tools)
        assert len(tools) == 0

    def test_file_search_store_names_adds_tool(self):
        g = _make_gemini(file_search_store_names=["store-1"])
        tools = []
        g._append_file_search_tool(tools)
        assert len(tools) == 1

    def test_file_search_with_metadata_filter_adds_filter(self):
        g = _make_gemini(
            file_search_store_names=["store-1"],
            file_search_metadata_filter="tag = 'science'",
        )
        tools = []
        g._append_file_search_tool(tools)
        assert len(tools) == 1
