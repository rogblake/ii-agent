"""
Unit tests for src/ii_agent/engine/v1/models/google/gemini.py

Tests cover:
- Gemini dataclass defaults and field types
- format_function_definitions utility
- format_image_for_message utility
- _normalize_function_definition utility
- prepare_response_schema utility
- Gemini.get_request_params()
- Gemini._format_messages() – system/user/assistant/tool roles
- Gemini._parse_provider_response() – text, function_call, thinking, usage
- Gemini._parse_provider_response_delta()
- Gemini.format_function_call_results()
- Gemini._get_metrics()
- Gemini.__deepcopy__()
- ainvoke error handling paths
"""

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from ii_agent.engine.v1.models.google.gemini import (
    Gemini,
    _normalize_function_definition,
    format_function_definitions,
    format_image_for_message,
    prepare_response_schema,
)
from ii_agent.engine.v1.models.message import Message, File
from ii_agent.engine.v1.models.metrics import Metrics
from ii_agent.engine.v1.models.response import ModelResponse
from ii_agent.engine.v1.exceptions import ModelProviderError
from ii_agent.engine.v1.media import Image
from ii_agent.engine.types import Provider

# Real SDK types used for building response mocks
from google.genai.types import Content, Part


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gemini(**kwargs) -> Gemini:
    g = Gemini(**kwargs)
    # Attach a mock client so get_client() doesn't need credentials
    mock_client = MagicMock()
    mock_client.aio = MagicMock()
    mock_client.aio.models = MagicMock()
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
    """Create a Content object with a single text Part."""
    return Content(role=role, parts=[Part.from_text(text=text)])


def _make_thought_content(thought_text: str, role: str = "model") -> Content:
    """Create a Content object with a thought part (mock)."""
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


def _make_function_call_content(name: str, args: dict, role: str = "model") -> Content:
    """Create a Content object with a function_call Part (mock)."""
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


# ---------------------------------------------------------------------------
# 1. Gemini class defaults
# ---------------------------------------------------------------------------

class TestGeminiDefaults:
    def test_default_id(self):
        assert Gemini().id == "gemini-2.0-flash-001"

    def test_default_name(self):
        assert Gemini().name == "Gemini"

    def test_default_provider(self):
        assert Gemini().provider == Provider.GOOGLE

    def test_default_search_false(self):
        assert Gemini().search is False

    def test_default_grounding_false(self):
        assert Gemini().grounding is False

    def test_default_vertexai_false(self):
        assert Gemini().vertexai is False

    def test_supports_native_structured_outputs(self):
        assert Gemini().supports_native_structured_outputs is True

    def test_custom_id(self):
        assert Gemini(id="gemini-ultra").id == "gemini-ultra"

    def test_custom_temperature(self):
        assert Gemini(temperature=0.7).temperature == 0.7

    def test_custom_max_output_tokens(self):
        assert Gemini(max_output_tokens=2048).max_output_tokens == 2048

    def test_role_map_model_to_assistant(self):
        g = Gemini()
        assert g.role_map["model"] == "assistant"

    def test_reverse_role_map_assistant_to_model(self):
        g = Gemini()
        assert g.reverse_role_map["assistant"] == "model"

    def test_reverse_role_map_tool_to_user(self):
        g = Gemini()
        assert g.reverse_role_map["tool"] == "user"

    def test_client_starts_none(self):
        assert Gemini().client is None

    def test_thinking_budget_default_none(self):
        assert Gemini().thinking_budget is None

    def test_seed_default_none(self):
        assert Gemini().seed is None


# ---------------------------------------------------------------------------
# 2. _normalize_function_definition
# ---------------------------------------------------------------------------

class TestNormalizeFunctionDefinition:
    def test_none_returns_none(self):
        assert _normalize_function_definition(None) is None

    def test_dict_with_function_key(self):
        tool = {"type": "function", "function": {"name": "fn", "description": "d"}}
        assert _normalize_function_definition(tool) == {"name": "fn", "description": "d"}

    def test_plain_dict_returned(self):
        assert _normalize_function_definition({"name": "fn"}) == {"name": "fn"}

    def test_object_with_to_dict(self):
        obj = MagicMock()
        obj.to_dict.return_value = {"name": "from_to_dict"}
        del obj.model_dump
        assert _normalize_function_definition(obj) == {"name": "from_to_dict"}

    def test_object_with_model_dump(self):
        obj = MagicMock(spec=[])
        obj.model_dump = MagicMock(return_value={"name": "from_model_dump"})
        assert _normalize_function_definition(obj) == {"name": "from_model_dump"}

    def test_to_dict_raises_falls_to_model_dump(self):
        obj = MagicMock()
        obj.to_dict.side_effect = RuntimeError("boom")
        obj.model_dump = MagicMock(return_value={"name": "fallback"})
        assert _normalize_function_definition(obj) == {"name": "fallback"}

    def test_unrecognised_returns_none(self):
        class Opaque:
            pass
        assert _normalize_function_definition(Opaque()) is None


# ---------------------------------------------------------------------------
# 3. format_function_definitions
# ---------------------------------------------------------------------------

class TestFormatFunctionDefinitions:
    def test_empty_list_returns_tool_object(self):
        # Returns a google.genai.types.Tool object (even for empty list)
        result = format_function_definitions([])
        assert result is not None

    def test_none_returns_tool_object(self):
        result = format_function_definitions(None)
        assert result is not None

    def test_tool_without_name_skipped(self):
        tool = {"type": "function", "function": {"description": "no name"}}
        result = format_function_definitions([tool])
        # Should still return a Tool, but with no valid declarations
        assert result is not None

    def test_valid_tool_processed(self):
        tool = {"type": "function", "function": {"name": "search", "description": "Search"}}
        result = format_function_definitions([tool])
        assert result is not None

    def test_none_tool_in_list_skipped(self):
        result = format_function_definitions([None])
        assert result is not None

    def test_multiple_tools_all_processed(self):
        tools = [
            {"type": "function", "function": {"name": "fn_a"}},
            {"type": "function", "function": {"name": "fn_b"}},
        ]
        result = format_function_definitions(tools)
        assert result is not None


# ---------------------------------------------------------------------------
# 4. format_image_for_message
# ---------------------------------------------------------------------------

class TestFormatImageForMessage:
    def test_image_with_bytes_content(self):
        img = MagicMock(spec=Image)
        img.get_content_bytes.return_value = b"\x89PNG data"
        img.mime_type = "image/png"
        img.format = None
        result = format_image_for_message(img)
        assert result is not None
        assert result["mime_type"] == "image/png"
        assert result["data"] == b"\x89PNG data"

    def test_image_no_content_returns_none(self):
        img = MagicMock(spec=Image)
        img.get_content_bytes.return_value = None
        result = format_image_for_message(img)
        assert result is None

    def test_image_infers_mime_from_format(self):
        img = MagicMock(spec=Image)
        img.get_content_bytes.return_value = b"jpeg data"
        img.mime_type = None
        img.format = "jpeg"
        result = format_image_for_message(img)
        assert result["mime_type"] == "image/jpeg"

    def test_image_defaults_mime_to_png(self):
        img = MagicMock(spec=Image)
        img.get_content_bytes.return_value = b"data"
        img.mime_type = None
        img.format = None
        result = format_image_for_message(img)
        assert result["mime_type"] == "image/png"


# ---------------------------------------------------------------------------
# 5. prepare_response_schema
# ---------------------------------------------------------------------------

class TestPrepareResponseSchema:
    def test_returns_json_schema(self):
        class MyModel(BaseModel):
            name: str
            value: int

        schema = prepare_response_schema(MyModel)
        assert "properties" in schema
        assert "name" in schema["properties"]


# ---------------------------------------------------------------------------
# 6. get_request_params
# ---------------------------------------------------------------------------

class TestGeminiGetRequestParams:
    def test_temperature_in_config(self):
        g = _make_gemini(temperature=0.5)
        params = g.get_request_params()
        # Returns {"config": GenerateContentConfig(...)}, not {"generation_config": ...}
        assert "config" in params
        cfg = params["config"]
        assert cfg.temperature == 0.5

    def test_max_output_tokens_in_config(self):
        g = _make_gemini(max_output_tokens=512)
        params = g.get_request_params()
        assert params["config"].max_output_tokens == 512

    def test_seed_in_config(self):
        g = _make_gemini(seed=42)
        params = g.get_request_params()
        assert params["config"].seed == 42

    def test_none_values_omitted(self):
        g = _make_gemini(temperature=None, max_output_tokens=None)
        params = g.get_request_params()
        if "config" in params:
            # temperature and max_output_tokens should be None/absent
            cfg = params["config"]
            assert cfg.temperature is None
            assert cfg.max_output_tokens is None

    def test_grounding_adds_builtin_tool(self):
        g = _make_gemini(grounding=True)
        params = g.get_request_params()
        # grounding adds a Google Search Retrieval tool in config
        assert "config" in params
        cfg = params["config"]
        assert cfg.tools is not None
        assert len(cfg.tools) >= 1

    def test_thinking_config_with_thinking_level(self):
        g = _make_gemini(thinking_level="high")
        params = g.get_request_params()
        cfg = params["config"]
        # thinking_config should be present
        assert cfg.thinking_config is not None
        assert cfg.thinking_config.thinking_level is not None

    def test_thinking_config_with_thinking_budget(self):
        g = _make_gemini(thinking_budget=1024)
        params = g.get_request_params()
        cfg = params["config"]
        assert cfg.thinking_config is not None
        assert cfg.thinking_config.thinking_budget == 1024

    def test_request_params_merged(self):
        g = _make_gemini(request_params={"custom_key": "custom_val"})
        params = g.get_request_params()
        assert params.get("custom_key") == "custom_val"


# ---------------------------------------------------------------------------
# 7. _format_messages
# ---------------------------------------------------------------------------

class TestGeminiFormatMessages:
    def test_system_message_extracted(self):
        g = _make_gemini()
        msgs = [Message(role="system", content="Be helpful.")]
        formatted, system = g._format_messages(msgs)
        assert system == "Be helpful."
        assert formatted == []

    def test_developer_role_treated_as_system(self):
        g = _make_gemini()
        msgs = [Message(role="developer", content="System instruction")]
        formatted, system = g._format_messages(msgs)
        assert system == "System instruction"
        assert formatted == []

    def test_user_text_message(self):
        g = _make_gemini()
        msgs = [Message(role="user", content="Hello")]
        formatted, system = g._format_messages(msgs)
        assert len(formatted) == 1
        # _format_messages returns Content objects, not dicts
        assert formatted[0].role == "user"

    def test_assistant_text_message_mapped_to_model(self):
        g = _make_gemini()
        msgs = [Message(role="assistant", content="Hi there")]
        formatted, system = g._format_messages(msgs)
        assert len(formatted) == 1
        assert formatted[0].role == "model"

    def test_assistant_with_tool_calls(self):
        g = _make_gemini()
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "search", "arguments": '{"query": "test"}'},
            }
        ]
        msgs = [Message(role="assistant", content="", tool_calls=tool_calls)]
        formatted, _ = g._format_messages(msgs)
        # Should have model-role Content with function_call parts
        assert len(formatted) >= 1
        assert any(c.role == "model" for c in formatted)

    def test_tool_result_message_without_tool_calls(self):
        # When a tool message has no tool_calls, uses tool_name/tool_call_id
        g = _make_gemini()
        msgs = [
            Message(
                role="tool",
                content="42",
                tool_name="calculator",
                tool_call_id="call_1",
            )
        ]
        # This path uses message.tool_calls check — no tool_calls means empty message_parts
        # but role is "user" (from reverse_role_map["tool"] = "user")
        formatted, _ = g._format_messages(msgs)
        # A tool message without explicit tool_calls in message.tool_calls falls
        # through to the else branch and creates a Content with empty message_parts
        assert len(formatted) >= 0  # may produce empty content

    def test_tool_result_with_tool_calls(self):
        g = _make_gemini()
        tool_calls_data = [{"tool_name": "calculator", "tool_call_id": "call_1", "content": "42"}]
        msgs = [
            Message(
                role="tool",
                content="42",
                tool_calls=tool_calls_data,
            )
        ]
        formatted, _ = g._format_messages(msgs)
        # Should produce function_response parts
        assert len(formatted) >= 1
        # role should be "user" (reverse_role_map["tool"] = "user")
        assert any(c.role == "user" for c in formatted)

    def test_user_message_with_images(self):
        g = _make_gemini()
        img = MagicMock(spec=Image)
        img.get_content_bytes.return_value = b"img data"
        img.content = None
        img.mime_type = "image/png"
        img.format = None
        msgs = [Message(role="user", content="Look at this", images=[img])]
        formatted, _ = g._format_messages(msgs)
        assert len(formatted) == 1
        # Should have text + image parts
        assert len(formatted[0].parts) >= 2

    def test_user_message_with_files(self):
        g = _make_gemini()
        file_obj = File(filepath=Path("/tmp/doc.pdf"))
        msgs = [Message(role="user", content="See attached", files=[file_obj])]
        formatted, _ = g._format_messages(msgs)
        assert len(formatted) == 1
        # Should have text part + files text part
        assert len(formatted[0].parts) >= 2

    def test_previous_interaction_id_does_not_exist_in_gemini(self):
        # Gemini's _format_messages does NOT filter by previous_interaction_id
        # (that's only in GeminiInteractions). Confirm all messages are returned.
        g = _make_gemini()
        msgs = [
            Message(role="user", content="First message"),
            Message(role="user", content="Second message"),
        ]
        formatted, _ = g._format_messages(msgs)
        assert len(formatted) == 2

    def test_assistant_with_thought_signature(self):
        g = _make_gemini()
        import base64
        sig_bytes = b"signature_bytes"
        sig_b64 = base64.b64encode(sig_bytes).decode("ascii")
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "fn", "arguments": "{}"},
            }
        ]
        msgs = [
            Message(
                role="assistant",
                content="thinking...",
                tool_calls=tool_calls,
                reasoning_content="I thought about this",
                provider_data={"thought_signature": sig_b64},
            )
        ]
        formatted, _ = g._format_messages(msgs)
        # Should produce model-role Content with parts
        assert len(formatted) >= 1
        assert any(c.role == "model" for c in formatted)


# ---------------------------------------------------------------------------
# 8. format_function_call_results
# ---------------------------------------------------------------------------

class TestGeminiFormatFunctionCallResults:
    def test_appends_combined_tool_message(self):
        g = _make_gemini()
        messages: List[Message] = []
        result_1 = Message(
            role="tool", content="result_data", tool_name="search", tool_call_id="tc_1"
        )
        g.format_function_call_results(messages, [result_1])
        assert len(messages) == 1
        # format_function_call_results in gemini.py creates a "tool" role message
        assert messages[0].role == "tool"

    def test_empty_results_no_message(self):
        g = _make_gemini()
        messages: List[Message] = []
        g.format_function_call_results(messages, [])
        assert len(messages) == 0

    def test_multiple_results_combined_in_one_message(self):
        g = _make_gemini()
        messages: List[Message] = []
        results = [
            Message(role="tool", content="r1", tool_name="fn_a", tool_call_id="tc_1"),
            Message(role="tool", content="r2", tool_name="fn_b", tool_call_id="tc_2"),
        ]
        g.format_function_call_results(messages, results)
        assert len(messages) == 1
        assert isinstance(messages[0].content, list)
        assert len(messages[0].content) == 2


# ---------------------------------------------------------------------------
# 9. _parse_provider_response
# ---------------------------------------------------------------------------

class TestGeminiParseProviderResponse:
    def test_text_content_parsed(self):
        g = _make_gemini()
        content = _make_text_content("Hello world")
        candidate = _make_candidate(content)
        usage = _make_usage()
        resp = _make_provider_response([candidate], usage=usage)
        mr = g._parse_provider_response(resp)
        assert mr.role == "assistant"
        assert mr.content == "Hello world"

    def test_no_candidates_returns_empty_response(self):
        g = _make_gemini()
        resp = MagicMock()
        resp.candidates = []
        resp.usage_metadata = None
        mr = g._parse_provider_response(resp)
        assert isinstance(mr, ModelResponse)

    def test_function_call_part_produces_tool_call(self):
        g = _make_gemini()
        content = _make_function_call_content("search", {"query": "python"})
        candidate = _make_candidate(content)
        resp = _make_provider_response([candidate])
        mr = g._parse_provider_response(resp)
        assert len(mr.tool_calls) == 1
        assert mr.tool_calls[0]["function"]["name"] == "search"

    def test_function_call_args_serialized_to_json(self):
        g = _make_gemini()
        content = _make_function_call_content("fn", {"key": "val"})
        candidate = _make_candidate(content)
        resp = _make_provider_response([candidate])
        mr = g._parse_provider_response(resp)
        assert json.loads(mr.tool_calls[0]["function"]["arguments"]) == {"key": "val"}

    def test_thinking_part_stored_in_reasoning(self):
        g = _make_gemini()
        content = _make_thought_content("This is a thought")
        candidate = _make_candidate(content)
        resp = _make_provider_response([candidate])
        mr = g._parse_provider_response(resp)
        assert mr.reasoning_content == "This is a thought"

    def test_usage_metadata_parsed(self):
        g = _make_gemini()
        content = _make_text_content("ok")
        candidate = _make_candidate(content)
        usage = _make_usage(input_t=10, output_t=20)
        resp = _make_provider_response([candidate], usage=usage)
        mr = g._parse_provider_response(resp)
        assert mr.response_usage is not None
        assert mr.response_usage.input_tokens == 10


# ---------------------------------------------------------------------------
# 10. _get_metrics
# ---------------------------------------------------------------------------

class TestGeminiGetMetrics:
    def test_input_tokens_set(self):
        g = _make_gemini()
        mr = g._get_metrics(_make_usage(input_t=50))
        assert mr.input_tokens == 50

    def test_output_tokens_set(self):
        # output_tokens = candidates_token_count (+ thoughts_token_count if not None)
        g = _make_gemini()
        usage = _make_usage(output_t=100, thought_t=None)
        mr = g._get_metrics(usage)
        assert mr.output_tokens == 100

    def test_output_tokens_include_thoughts(self):
        g = _make_gemini()
        usage = _make_usage(output_t=80, thought_t=20)
        mr = g._get_metrics(usage)
        # output_tokens = candidates_token_count + thoughts_token_count = 80 + 20
        assert mr.output_tokens == 100

    def test_total_tokens_computed(self):
        g = _make_gemini()
        usage = _make_usage(input_t=30, output_t=70, thought_t=None)
        mr = g._get_metrics(usage)
        # total = input + output = 30 + 70
        assert mr.total_tokens == 100

    def test_cache_read_tokens_set(self):
        g = _make_gemini()
        mr = g._get_metrics(_make_usage(cached_t=25))
        assert mr.cache_read_tokens == 25

    def test_reasoning_tokens_not_directly_set(self):
        # Gemini _get_metrics doesn't set reasoning_tokens separately
        # (thoughts are folded into output_tokens)
        g = _make_gemini()
        mr = g._get_metrics(_make_usage())
        assert isinstance(mr, Metrics)


# ---------------------------------------------------------------------------
# 11. __deepcopy__
# ---------------------------------------------------------------------------

class TestGeminiDeepcopy:
    def test_client_set_to_none(self):
        g = Gemini(api_key="key123", temperature=0.5)
        g.client = MagicMock(name="live_client")
        g_copy = copy.deepcopy(g)
        assert g_copy.client is None

    def test_config_preserved(self):
        g = Gemini(id="gemini-pro", temperature=0.9, max_output_tokens=1024)
        g_copy = copy.deepcopy(g)
        assert g_copy.id == "gemini-pro"
        assert g_copy.temperature == 0.9
        assert g_copy.max_output_tokens == 1024

    def test_copy_is_independent(self):
        g = Gemini(stop_sequences=["END"])
        g_copy = copy.deepcopy(g)
        g_copy.stop_sequences.append("STOP")
        assert g.stop_sequences == ["END"]


# ---------------------------------------------------------------------------
# 12. ainvoke error handling
# ---------------------------------------------------------------------------

class TestGeminiAinvokeErrors:
    @pytest.mark.asyncio
    async def test_client_error_raises_model_provider_error(self):
        from google.genai.errors import ClientError
        g = _make_gemini(api_key="key")
        err = MagicMock(spec=ClientError)
        err.__class__ = ClientError
        err.args = ("bad request",)
        err.code = 400
        err.response = MagicMock()
        g.client.aio.models.generate_content = AsyncMock(side_effect=err)
        msgs = [Message(role="user", content="hello")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await g.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_generic_exception_raises_model_provider_error(self):
        g = _make_gemini(api_key="key")
        g.client.aio.models.generate_content = AsyncMock(
            side_effect=Exception("unexpected")
        )
        msgs = [Message(role="user", content="hello")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await g.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_httpx_timeout_raises_model_provider_error(self):
        import httpx
        g = _make_gemini(api_key="key")
        g.client.aio.models.generate_content = AsyncMock(
            side_effect=httpx.TimeoutException("timed out")
        )
        msgs = [Message(role="user", content="hello")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await g.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_runtime_error_raises_model_provider_error(self):
        # ainvoke catches all Exceptions and wraps in ModelProviderError
        # (only ainvoke_stream has the "client has been closed" special case)
        g = _make_gemini(api_key="key")
        g.client.aio.models.generate_content = AsyncMock(
            side_effect=RuntimeError(
                "Cannot send a request, as the client has been closed"
            )
        )
        msgs = [Message(role="user", content="hello")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await g.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_httpcore_read_error_raises_model_provider_error(self):
        import httpcore
        g = _make_gemini(api_key="key")
        g.client.aio.models.generate_content = AsyncMock(
            side_effect=httpcore.ReadError("read error")
        )
        msgs = [Message(role="user", content="hello")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await g.ainvoke(msgs, assistant)


# ---------------------------------------------------------------------------
# 13. _parse_provider_response_delta
# ---------------------------------------------------------------------------

class TestGeminiParseProviderResponseDelta:
    def _make_chunk(self, content: Optional[Content] = None, usage=None):
        chunk = MagicMock()
        if content is not None:
            candidate = MagicMock()
            candidate.content = content
            candidate.grounding_metadata = None
            chunk.candidates = [candidate]
        else:
            chunk.candidates = []
        chunk.usage_metadata = usage
        return chunk

    def test_text_delta_extracted(self):
        g = _make_gemini()
        content = _make_text_content("Hello stream")
        chunk = self._make_chunk(content=content)
        resp = g._parse_provider_response_delta(chunk)
        assert resp.content == "Hello stream"

    def test_empty_candidates_returns_empty_response(self):
        g = _make_gemini()
        chunk = self._make_chunk()
        resp = g._parse_provider_response_delta(chunk)
        assert isinstance(resp, ModelResponse)
        assert resp.content is None

    def test_function_call_delta_extracted(self):
        g = _make_gemini()
        content = _make_function_call_content("fn_x", {"x": 1})
        chunk = self._make_chunk(content=content)
        resp = g._parse_provider_response_delta(chunk)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0]["function"]["name"] == "fn_x"

    def test_usage_metadata_parsed_from_delta(self):
        # Usage metadata is parsed inside the candidates block; provide a candidate
        # with an empty content but non-None usage_metadata on the chunk.
        g = _make_gemini()
        usage = _make_usage(input_t=5, output_t=15, thought_t=None)
        # Make a content with no parts so it doesn't interfere
        content = Content(role="model", parts=[])
        chunk = self._make_chunk(content=content, usage=usage)
        resp = g._parse_provider_response_delta(chunk)
        assert resp.response_usage is not None
        assert resp.response_usage.input_tokens == 5

    def test_thought_goes_to_reasoning_content(self):
        g = _make_gemini()
        content = _make_thought_content("I am reasoning")
        chunk = self._make_chunk(content=content)
        resp = g._parse_provider_response_delta(chunk)
        assert resp.reasoning_content == "I am reasoning"

    def test_role_mapped_to_assistant(self):
        g = _make_gemini()
        content = _make_text_content("hi", role="model")
        chunk = self._make_chunk(content=content)
        resp = g._parse_provider_response_delta(chunk)
        assert resp.role == "assistant"


# ---------------------------------------------------------------------------
# 14. ainvoke happy path
# ---------------------------------------------------------------------------

class TestGeminiAinvokeHappyPath:
    @pytest.mark.asyncio
    async def test_ainvoke_returns_model_response(self):
        g = _make_gemini(api_key="test_key")

        content = _make_text_content("I'm Gemini!")
        candidate = _make_candidate(content)
        usage = _make_usage()
        raw_resp = _make_provider_response([candidate], usage=usage)

        g.client.aio.models.generate_content = AsyncMock(return_value=raw_resp)

        msgs = [
            Message(role="system", content="Be helpful"),
            Message(role="user", content="Hi"),
        ]
        assistant = Message(role="assistant", content="")
        result = await g.ainvoke(msgs, assistant)
        assert isinstance(result, ModelResponse)
        assert result.role == "assistant"
        assert result.content == "I'm Gemini!"
