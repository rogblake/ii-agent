"""
Unit tests for src/ii_agent/agent/runtime/models/anthropic/claude.py

Tests cover:
- ROLE_MAP constant
- MCPServerConfiguration dataclass
- _normalize_tool_definition utility
- format_tools_for_model utility
- format_messages() – all role branches, caching, tool results
- Claude class defaults and instantiation
- Claude._setup_skills_configuration()
- Claude._ensure_additional_properties_false()
- Claude._build_output_format()
- Claude.get_request_params()
- Claude._prepare_request_kwargs()
- Claude._parse_provider_response() – text, thinking, tool_use, citations, usage
- ainvoke error handling paths
- ainvoke happy path
"""

import json
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


def _make_usage(input_t=10, output_t=20, cache_create=5, cache_read=3):
    usage = MagicMock()
    usage.input_tokens = input_t
    usage.output_tokens = output_t
    usage.cache_creation_input_tokens = cache_create
    usage.cache_read_input_tokens = cache_read
    usage.model_dump = MagicMock(
        return_value={"input_tokens": input_t, "output_tokens": output_t}
    )
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
# 1. ROLE_MAP
# ---------------------------------------------------------------------------

class TestRoleMap:
    def test_system_maps_to_system(self):
        assert ROLE_MAP["system"] == "system"

    def test_developer_maps_to_system(self):
        assert ROLE_MAP["developer"] == "system"

    def test_user_maps_to_user(self):
        assert ROLE_MAP["user"] == "user"

    def test_assistant_maps_to_assistant(self):
        assert ROLE_MAP["assistant"] == "assistant"

    def test_tool_maps_to_user(self):
        assert ROLE_MAP["tool"] == "user"


# ---------------------------------------------------------------------------
# 2. MCPServerConfiguration
# ---------------------------------------------------------------------------

class TestMCPServerConfiguration:
    def test_required_fields(self):
        mcp = MCPServerConfiguration(name="my_server", url="https://mcp.example.com")
        assert mcp.name == "my_server"
        assert mcp.url == "https://mcp.example.com"

    def test_optional_api_key(self):
        mcp = MCPServerConfiguration(name="s", url="u", api_key="secret")
        assert mcp.api_key == "secret"

    def test_optional_headers(self):
        mcp = MCPServerConfiguration(name="s", url="u", headers={"X-Auth": "token"})
        assert mcp.headers == {"X-Auth": "token"}

    def test_defaults_none(self):
        mcp = MCPServerConfiguration(name="s", url="u")
        assert mcp.api_key is None
        assert mcp.metadata is None
        assert mcp.headers is None


# ---------------------------------------------------------------------------
# 3. _normalize_tool_definition
# ---------------------------------------------------------------------------

class TestNormalizeToolDefinition:
    def test_none_returns_none(self):
        assert _normalize_tool_definition(None) is None

    def test_dict_with_function_key(self):
        tool = {"type": "function", "function": {"name": "fn", "description": "d"}}
        assert _normalize_tool_definition(tool) == {"name": "fn", "description": "d"}

    def test_plain_dict_returned(self):
        assert _normalize_tool_definition({"name": "fn"}) == {"name": "fn"}

    def test_object_with_to_dict(self):
        obj = MagicMock()
        obj.to_dict.return_value = {"name": "from_to_dict"}
        del obj.model_dump
        assert _normalize_tool_definition(obj) == {"name": "from_to_dict"}

    def test_object_with_model_dump(self):
        obj = MagicMock(spec=[])
        obj.model_dump = MagicMock(return_value={"name": "from_model_dump"})
        assert _normalize_tool_definition(obj) == {"name": "from_model_dump"}

    def test_unrecognised_returns_none(self):
        assert _normalize_tool_definition(object()) is None


# ---------------------------------------------------------------------------
# 4. format_tools_for_model
# ---------------------------------------------------------------------------

class TestFormatToolsForModel:
    def test_empty_tools(self):
        assert format_tools_for_model([]) == []

    def test_none_tools(self):
        assert format_tools_for_model(None) == []

    def test_valid_tool_formatted(self):
        tools = [{"name": "search", "description": "Search", "parameters": {"type": "object", "properties": {}}}]
        result = format_tools_for_model(tools)
        assert len(result) == 1
        assert result[0]["name"] == "search"
        assert result[0]["input_schema"] == {"type": "object", "properties": {}}

    def test_tool_without_parameters_defaults_empty(self):
        tools = [{"name": "fn", "description": "A function"}]
        result = format_tools_for_model(tools)
        assert result[0]["input_schema"] == {"type": "object", "properties": {}}

    def test_wrapped_tool_format(self):
        tools = [{"type": "function", "function": {"name": "fn", "description": "desc"}}]
        result = format_tools_for_model(tools)
        assert len(result) == 1
        assert result[0]["name"] == "fn"

    def test_tool_without_name_skipped(self):
        tools = [{"description": "no name"}]
        result = format_tools_for_model(tools)
        assert result == []

    def test_multiple_tools(self):
        tools = [
            {"name": "fn_a", "description": "A"},
            {"name": "fn_b", "description": "B"},
        ]
        result = format_tools_for_model(tools)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# 5. format_messages
# ---------------------------------------------------------------------------

class TestFormatMessages:
    def test_system_message_extracted(self):
        msgs = [Message(role="system", content="Be helpful")]
        formatted, system = format_messages(msgs)
        assert system == "Be helpful"
        assert not any(m.get("role") == "system" for m in formatted)

    def test_system_message_list_content(self):
        msgs = [Message(role="system", content=[{"text": "Part1"}, {"text": "Part2"}])]
        _, system = format_messages(msgs)
        assert "Part1" in system
        assert "Part2" in system

    def test_user_message_formatted(self):
        msgs = [Message(role="user", content="Hello")]
        formatted, _ = format_messages(msgs)
        assert formatted[0]["role"] == "user"
        assert any(p.get("type") == "text" for p in formatted[0]["content"])

    def test_assistant_message_formatted(self):
        msgs = [Message(role="assistant", content="Hi")]
        formatted, _ = format_messages(msgs)
        assert formatted[0]["role"] == "assistant"

    def test_tool_result_collected_into_user_message(self):
        msgs = [
            Message(role="user", content="Hello"),
            Message(role="tool", content="tool result", tool_call_id="tc_1"),
        ]
        formatted, _ = format_messages(msgs)
        tool_result_msgs = [
            m for m in formatted
            if m.get("role") == "user" and isinstance(m.get("content"), list)
            and any(c.get("type") == "tool_result" for c in m["content"])
        ]
        assert len(tool_result_msgs) >= 1

    def test_tool_result_flushed_before_assistant(self):
        msgs = [
            Message(role="tool", content="result", tool_call_id="tc_1"),
            Message(role="assistant", content="OK"),
        ]
        formatted, _ = format_messages(msgs)
        assert len(formatted) == 2
        assert formatted[0]["role"] == "user"
        assert formatted[1]["role"] == "assistant"

    def test_assistant_with_reasoning_and_signature(self):
        msgs = [
            Message(
                role="assistant",
                content="Answer",
                reasoning_content="I reasoned",
                provider_data={"signature": "sig_abc"},
            )
        ]
        formatted, _ = format_messages(msgs)
        parts = formatted[0]["content"]
        thinking_parts = [p for p in parts if p.get("type") == "thinking"]
        assert len(thinking_parts) == 1
        assert thinking_parts[0]["signature"] == "sig_abc"

    def test_assistant_with_redacted_reasoning(self):
        msgs = [
            Message(
                role="assistant",
                content="Answer",
                redacted_reasoning_content="<redacted>",
            )
        ]
        formatted, _ = format_messages(msgs)
        parts = formatted[0]["content"]
        redacted_parts = [p for p in parts if p.get("type") == "redacted_thinking"]
        assert len(redacted_parts) == 1

    def test_assistant_with_tool_calls(self):
        tool_calls = [
            {
                "id": "tc_1",
                "type": "function",
                "function": {"name": "search", "arguments": '{"q": "test"}'},
            }
        ]
        msgs = [Message(role="assistant", content="", tool_calls=tool_calls)]
        formatted, _ = format_messages(msgs)
        parts = formatted[0]["content"]
        tool_use_parts = [p for p in parts if p.get("type") == "tool_use"]
        assert len(tool_use_parts) == 1
        assert tool_use_parts[0]["name"] == "search"

    def test_cache_conversation_adds_cache_control(self):
        msgs = [
            Message(role="user", content="Q1"),
            Message(role="assistant", content="A1"),
            Message(role="user", content="Q2"),
        ]
        formatted, _ = format_messages(msgs, cache_conversation=True)
        all_parts = []
        for m in formatted:
            if isinstance(m.get("content"), list):
                all_parts.extend(m["content"])
        cache_ctrl_parts = [p for p in all_parts if "cache_control" in p]
        assert len(cache_ctrl_parts) >= 1

    def test_developer_role_creates_system_chat_message(self):
        # "developer" is NOT extracted as a system_message string.
        # It becomes a chat message with role "system" via ROLE_MAP.
        msgs = [Message(role="developer", content="Developer instruction")]
        formatted, system = format_messages(msgs)
        assert system is None
        assert any(m.get("role") == "system" for m in formatted)

    def test_remaining_tool_results_flushed(self):
        msgs = [Message(role="tool", content="leftover result", tool_call_id="tc_99")]
        formatted, _ = format_messages(msgs)
        assert any(m["role"] == "user" for m in formatted)

    def test_empty_messages(self):
        formatted, system = format_messages([])
        assert formatted == []
        assert system is None


# ---------------------------------------------------------------------------
# 6. Claude class defaults
# ---------------------------------------------------------------------------

class TestClaudeDefaults:
    def test_default_id(self):
        c = Claude()
        assert "claude" in c.id.lower()

    def test_default_name(self):
        assert Claude().name == "Claude"

    def test_default_provider(self):
        assert Claude().provider == Provider.ANTHROPIC

    def test_default_max_tokens(self):
        assert Claude().max_tokens == 8192

    def test_default_temperature_none(self):
        assert Claude().temperature is None

    def test_default_cache_system_prompt_false(self):
        assert Claude().cache_system_prompt is False

    def test_default_cache_conversation_false(self):
        assert Claude().cache_conversation is False

    def test_custom_api_key(self):
        assert Claude(api_key="my_api_key").api_key == "my_api_key"

    def test_client_starts_none(self):
        assert Claude().client is None

    def test_async_client_starts_none(self):
        assert Claude().async_client is None


# ---------------------------------------------------------------------------
# 7. Claude._setup_skills_configuration
# ---------------------------------------------------------------------------

class TestClaudeSkillsConfiguration:
    def test_skills_trigger_betas_setup(self):
        c = Claude(skills=[{"type": "anthropic", "skill_id": "pptx", "version": "latest"}])
        assert c.betas is not None
        assert "skills-2025-10-02" in c.betas
        assert "code-execution-2025-08-25" in c.betas

    def test_skills_merge_with_existing_betas(self):
        c = Claude(
            skills=[{"type": "anthropic", "skill_id": "pdf"}],
            betas=["existing-beta"],
        )
        assert "existing-beta" in c.betas
        assert "skills-2025-10-02" in c.betas

    def test_no_skills_no_betas_modification(self):
        c = Claude()
        assert c.betas is None

    def test_skills_not_duplicated_in_betas(self):
        c = Claude(
            skills=[{"type": "anthropic", "skill_id": "pdf"}],
            betas=["skills-2025-10-02"],
        )
        assert c.betas.count("skills-2025-10-02") == 1


# ---------------------------------------------------------------------------
# 8. Claude._ensure_additional_properties_false
# ---------------------------------------------------------------------------

class TestClaudeEnsureAdditionalPropertiesFalse:
    def test_object_type_gets_false(self):
        c = Claude()
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        c._ensure_additional_properties_false(schema)
        assert schema["additionalProperties"] is False

    def test_top_level_object_gets_additional_properties_false(self):
        # _ensure_additional_properties_false processes the schema dict itself.
        # It does NOT recurse into individual property values in "properties" dict.
        # It recurses into the "properties" key's value dict, but only checks
        # if THAT dict has type=="object". Individual properties are skipped.
        c = Claude()
        schema = {"type": "object", "properties": {}}
        c._ensure_additional_properties_false(schema)
        assert schema["additionalProperties"] is False

    def test_non_object_unchanged(self):
        c = Claude()
        schema = {"type": "string"}
        c._ensure_additional_properties_false(schema)
        assert "additionalProperties" not in schema

    def test_array_items_processed(self):
        c = Claude()
        schema = {"type": "array", "items": {"type": "object", "properties": {}}}
        c._ensure_additional_properties_false(schema)
        assert schema["items"]["additionalProperties"] is False


# ---------------------------------------------------------------------------
# 9. Claude._build_output_format
# ---------------------------------------------------------------------------

class TestClaudeBuildOutputFormat:
    def test_none_returns_none(self):
        assert Claude()._build_output_format(None) is None

    def test_pydantic_model_returns_json_schema(self):
        class TestModel(BaseModel):
            value: str

        c = Claude()
        result = c._build_output_format(TestModel)
        assert result is not None
        assert result["type"] == "json_schema"
        assert "schema" in result

    def test_dict_format_returned_unchanged(self):
        c = Claude()
        fmt = {"type": "json_schema", "schema": {"type": "object"}}
        assert c._build_output_format(fmt) == fmt

    def test_pydantic_model_fallback_adds_additional_properties(self):
        # The fallback path executes when transform_schema raises ImportError.
        # transform_schema is imported locally inside the try block, so we
        # patch it at the anthropic module level.
        class MyModel(BaseModel):
            name: str

        c = Claude()
        with patch("anthropic.transform_schema", side_effect=ImportError()):
            result = c._build_output_format(MyModel)
        assert result["schema"]["additionalProperties"] is False


# ---------------------------------------------------------------------------
# 10. Claude.get_request_params
# ---------------------------------------------------------------------------

class TestClaudeGetRequestParams:
    def test_max_tokens_included(self):
        c = Claude(max_tokens=4096)
        assert c.get_request_params()["max_tokens"] == 4096

    def test_temperature_included_when_set(self):
        c = Claude(temperature=0.5)
        assert c.get_request_params()["temperature"] == 0.5

    def test_stop_sequences_included(self):
        c = Claude(stop_sequences=["STOP"])
        assert c.get_request_params()["stop_sequences"] == ["STOP"]

    def test_top_p_included(self):
        c = Claude(top_p=0.9)
        assert c.get_request_params()["top_p"] == 0.9

    def test_top_k_included(self):
        c = Claude(top_k=40)
        assert c.get_request_params()["top_k"] == 40

    def test_betas_included(self):
        c = Claude(betas=["beta_1", "beta_2"])
        params = c.get_request_params()
        assert "betas" in params
        assert "beta_1" in params["betas"]

    def test_context_management_included(self):
        c = Claude(context_management={"max_tokens": 100000})
        assert c.get_request_params()["context_management"] == {"max_tokens": 100000}

    def test_mcp_servers_included(self):
        mcp = MCPServerConfiguration(name="mcp_server", url="https://mcp.example.com")
        c = Claude(mcp_servers=[mcp])
        params = c.get_request_params()
        assert "mcp_servers" in params
        assert len(params["mcp_servers"]) == 1
        assert params["mcp_servers"][0]["name"] == "mcp_server"

    def test_request_params_merged(self):
        c = Claude(request_params={"custom": "value"})
        assert c.get_request_params()["custom"] == "value"

    def test_thinking_included_when_set(self):
        c = Claude(thinking={"type": "enabled", "budget_tokens": 1024})
        assert "thinking" in c.get_request_params()

    def test_skills_adds_container(self):
        c = Claude(skills=[{"type": "anthropic", "skill_id": "pptx", "version": "latest"}])
        params = c.get_request_params()
        assert "container" in params
        assert params["container"]["skills"] is not None


# ---------------------------------------------------------------------------
# 11. Claude._prepare_request_kwargs
# ---------------------------------------------------------------------------

class TestClaudePrepareRequestKwargs:
    def test_system_message_included(self):
        c = Claude()
        kwargs = c._prepare_request_kwargs("Be helpful")
        assert "system" in kwargs
        assert kwargs["system"][0]["text"] == "Be helpful"
        assert kwargs["system"][0]["type"] == "text"

    def test_system_with_cache_control(self):
        c = Claude(cache_system_prompt=True)
        kwargs = c._prepare_request_kwargs("System message")
        assert "cache_control" in kwargs["system"][0]

    def test_system_with_extended_cache(self):
        c = Claude(cache_system_prompt=True, extended_cache_time=True)
        kwargs = c._prepare_request_kwargs("System")
        assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}

    def test_tools_formatted_and_included(self):
        c = Claude()
        tools = [{"name": "search", "description": "Search"}]
        kwargs = c._prepare_request_kwargs("System", tools=tools)
        assert "tools" in kwargs

    def test_response_format_builds_output_format(self):
        class MySchema(BaseModel):
            result: str

        c = Claude()
        kwargs = c._prepare_request_kwargs("System", response_format=MySchema)
        assert "output_format" in kwargs

    def test_skills_adds_code_execution_tool(self):
        # format_tools_for_model normalizes tools and strips the "type" field.
        # The code_execution tool is identified by its name after formatting.
        c = Claude(skills=[{"type": "anthropic", "skill_id": "pptx", "version": "latest"}])
        kwargs = c._prepare_request_kwargs("System", tools=[{"name": "fn"}])
        tool_names = [t.get("name") for t in kwargs.get("tools", [])]
        assert "code_execution" in tool_names

    def test_empty_system_message_not_included(self):
        c = Claude()
        kwargs = c._prepare_request_kwargs("")
        assert "system" not in kwargs


# ---------------------------------------------------------------------------
# 12. Claude._parse_provider_response
# ---------------------------------------------------------------------------

class TestClaudeParseProviderResponse:
    def test_role_set_to_assistant(self):
        c = _make_claude()
        text_block = _make_response_block("text", text="Hello", citations=None)
        mr = c._parse_provider_response(_make_provider_response([text_block]))
        assert mr.role == "assistant"

    def test_text_content_extracted(self):
        c = _make_claude()
        text_block = _make_response_block("text", text="Hello world", citations=None)
        mr = c._parse_provider_response(_make_provider_response([text_block]))
        assert mr.content == "Hello world"

    def test_multiple_text_blocks_concatenated(self):
        c = _make_claude()
        block1 = _make_response_block("text", text="Part 1 ", citations=None)
        block2 = _make_response_block("text", text="Part 2", citations=None)
        mr = c._parse_provider_response(_make_provider_response([block1, block2]))
        assert mr.content == "Part 1 Part 2"

    def test_thinking_block_stored_in_reasoning(self):
        c = _make_claude()
        thinking_block = _make_response_block(
            "thinking", thinking="I am thinking", signature="sig_abc"
        )
        mr = c._parse_provider_response(_make_provider_response([thinking_block]))
        assert mr.reasoning_content == "I am thinking"
        assert mr.provider_data["signature"] == "sig_abc"

    def test_redacted_thinking_block(self):
        c = _make_claude()
        redacted_block = _make_response_block("redacted_thinking", data="<redacted data>")
        mr = c._parse_provider_response(_make_provider_response([redacted_block]))
        assert mr.redacted_reasoning_content == "<redacted data>"

    def test_tool_use_extracted(self):
        c = _make_claude()
        tool_block = _make_response_block(
            "tool_use", id="tc_1", name="search", input={"query": "test"}, citations=None
        )
        text_block = _make_response_block("text", text="Using tool", citations=None)
        mr = c._parse_provider_response(
            _make_provider_response([text_block, tool_block], stop_reason="tool_use")
        )
        assert len(mr.tool_calls) == 1
        assert mr.tool_calls[0]["function"]["name"] == "search"
        assert mr.tool_calls[0]["id"] == "tc_1"

    def test_tool_input_serialized_to_json(self):
        c = _make_claude()
        tool_block = _make_response_block(
            "tool_use", id="tc_1", name="fn", input={"key": "value"}, citations=None
        )
        mr = c._parse_provider_response(
            _make_provider_response([tool_block], stop_reason="tool_use")
        )
        args = json.loads(mr.tool_calls[0]["function"]["arguments"])
        assert args == {"key": "value"}

    def test_web_search_citation_extracted(self):
        from anthropic.types import CitationsWebSearchResultLocation
        c = _make_claude()
        citation = MagicMock(spec=CitationsWebSearchResultLocation)
        citation.url = "https://example.com"
        citation.cited_text = "cited search text"
        citation.model_dump = MagicMock(return_value={"type": "web_search"})
        text_block = _make_response_block("text", text="Cited text", citations=[citation])
        mr = c._parse_provider_response(_make_provider_response([text_block]))
        assert mr.citations is not None
        assert mr.citations.urls is not None

    def test_document_citation_extracted(self):
        from anthropic.types import CitationPageLocation
        c = _make_claude()
        citation = MagicMock(spec=CitationPageLocation)
        citation.document_title = "Test Doc"
        citation.cited_text = "cited text"
        citation.model_dump = MagicMock(return_value={"type": "document"})
        text_block = _make_response_block("text", text="Cited text", citations=[citation])
        mr = c._parse_provider_response(_make_provider_response([text_block]))
        assert mr.citations is not None
        assert mr.citations.documents is not None

    def test_usage_metrics_extracted(self):
        c = _make_claude()
        text_block = _make_response_block("text", text="Hi", citations=None)
        usage = _make_usage(input_t=10, output_t=20)
        mr = c._parse_provider_response(_make_provider_response([text_block], usage=usage))
        assert mr.response_usage is not None
        assert mr.response_usage.input_tokens == 10
        assert mr.response_usage.output_tokens == 20

    def test_empty_content_array(self):
        c = _make_claude()
        mr = c._parse_provider_response(_make_provider_response([]))
        assert isinstance(mr, ModelResponse)


# ---------------------------------------------------------------------------
# 13. ainvoke error handling
# ---------------------------------------------------------------------------

class TestClaudeAinvokeErrors:
    @pytest.mark.asyncio
    async def test_api_connection_error_raises_model_provider_error(self):
        from anthropic import APIConnectionError
        c = _make_claude(api_key="key")
        err = MagicMock(spec=APIConnectionError)
        err.__class__ = APIConnectionError
        err.message = "connection error"
        c.async_client.beta.messages.create = AsyncMock(side_effect=err)
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await c.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_rate_limit_error_raises_model_rate_limit_error(self):
        from anthropic import RateLimitError
        import httpx
        c = _make_claude(api_key="key")
        # Use a real RateLimitError instance so `raise ... from e` works
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 429
        mock_response.headers = {}
        err = RateLimitError("rate limited", response=mock_response, body=None)
        c.async_client.beta.messages.create = AsyncMock(side_effect=err)
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelRateLimitError):
            await c.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_api_status_error_raises_model_provider_error(self):
        from anthropic import APIStatusError
        c = _make_claude(api_key="key")
        err = MagicMock(spec=APIStatusError)
        err.__class__ = APIStatusError
        err.message = "status error"
        err.status_code = 500
        c.async_client.beta.messages.create = AsyncMock(side_effect=err)
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await c.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_generic_exception_raises_model_provider_error(self):
        c = _make_claude(api_key="key")
        c.async_client.beta.messages.create = AsyncMock(
            side_effect=ValueError("unexpected error")
        )
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await c.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_httpx_timeout_raises_model_provider_error(self):
        import httpx
        c = _make_claude(api_key="key")
        c.async_client.beta.messages.create = AsyncMock(
            side_effect=httpx.TimeoutException("timed out")
        )
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await c.ainvoke(msgs, assistant)


# ---------------------------------------------------------------------------
# 14. Claude.get_system_message_for_model
# ---------------------------------------------------------------------------

class TestClaudeGetSystemMessageForModel:
    def test_with_tools_returns_string(self):
        c = Claude()
        msg = c.get_system_message_for_model(tools=[{"name": "fn"}])
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_without_tools_returns_none(self):
        assert Claude().get_system_message_for_model(tools=None) is None

    def test_empty_tools_returns_none(self):
        assert Claude().get_system_message_for_model(tools=[]) is None


# ---------------------------------------------------------------------------
# 15. Claude ainvoke happy path
# ---------------------------------------------------------------------------

class TestClaudeAinvokeHappyPath:
    @pytest.mark.asyncio
    async def test_ainvoke_returns_model_response(self):
        c = _make_claude(api_key="test_key")
        text_block = _make_response_block("text", text="Hello from Claude!", citations=None)
        provider_resp = _make_provider_response(
            [text_block], stop_reason="end_turn", role="assistant", usage=_make_usage()
        )
        c.async_client.beta.messages.create = AsyncMock(return_value=provider_resp)

        msgs = [
            Message(role="system", content="Be helpful"),
            Message(role="user", content="Hi"),
        ]
        assistant = Message(role="assistant", content="")
        result = await c.ainvoke(msgs, assistant)
        assert isinstance(result, ModelResponse)
        assert result.role == "assistant"
        assert result.content == "Hello from Claude!"
