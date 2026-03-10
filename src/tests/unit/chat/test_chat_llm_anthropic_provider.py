"""Unit tests for ii_agent.chat.llm.anthropic.provider (AnthropicProvider)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.chat.types import (
    BinaryContent,
    Message,
    MessageRole,
    TextContent,
    ToolCall,
    ToolResult,
    TextResultContent,
    FinishReason,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


import uuid as _uuid_mod

_SESSION_ID = "test-session-abc"


def _make_llm_config(
    model: str = "claude-3-5-sonnet-20241022",
    api_key: str = "test-key",
    temperature: Optional[float] = None,
    thinking_tokens: Optional[int] = None,
    enable_prompt_caching: bool = True,
    vertex_project_id: Optional[str] = None,
    vertex_region: Optional[str] = None,
    base_url: Optional[str] = None,
) -> LLMConfig:
    kwargs: Dict[str, Any] = dict(
        model=model,
        api_type="anthropic",
        api_key=SecretStr(api_key),
        enable_prompt_caching=enable_prompt_caching,
    )
    if temperature is not None:
        kwargs["temperature"] = temperature
    if thinking_tokens is not None:
        kwargs["thinking_tokens"] = thinking_tokens
    if vertex_project_id is not None:
        kwargs["vertex_project_id"] = vertex_project_id
    if vertex_region is not None:
        kwargs["vertex_region"] = vertex_region
    if base_url is not None:
        kwargs["base_url"] = base_url
    return LLMConfig(**kwargs)


def _make_user_message(text: str = "Hello") -> Message:
    return Message(
        id=_uuid_mod.uuid4(),
        session_id=_SESSION_ID,
        role=MessageRole.USER,
        parts=[TextContent(text=text)],
    )


def _make_assistant_message(text: str = "Hi") -> Message:
    return Message(
        id=_uuid_mod.uuid4(),
        session_id=_SESSION_ID,
        role=MessageRole.ASSISTANT,
        parts=[TextContent(text=text)],
    )


# ---------------------------------------------------------------------------
# SkillConfig / ContainerConfig schemas
# ---------------------------------------------------------------------------


class TestSkillConfig:
    def test_default_type_is_anthropic(self):
        from ii_agent.chat.llm.anthropic.provider import SkillConfig

        sc = SkillConfig(skill_id="pdf", version="latest")
        assert sc.type == "anthropic"

    def test_custom_type(self):
        from ii_agent.chat.llm.anthropic.provider import SkillConfig

        sc = SkillConfig(type="custom", skill_id="my_skill", version="1.0")
        assert sc.type == "custom"

    def test_default_version(self):
        from ii_agent.chat.llm.anthropic.provider import SkillConfig

        sc = SkillConfig(skill_id="xlsx")
        assert sc.version == "latest"


class TestContainerConfig:
    def test_container_config_class_exists(self):
        from ii_agent.chat.llm.anthropic.provider import ContainerConfig

        # ContainerConfig uses @dataclass + BaseModel (non-standard) - verify class is importable
        assert ContainerConfig is not None
        assert hasattr(ContainerConfig, "__dataclass_fields__") or hasattr(
            ContainerConfig, "__fields__"
        )

    def test_container_config_has_skills_and_id_fields(self):
        from ii_agent.chat.llm.anthropic.provider import ContainerConfig

        # The class definition has skills and id as attributes
        annotations = ContainerConfig.__annotations__
        assert "skills" in annotations
        assert "id" in annotations


# ---------------------------------------------------------------------------
# FileResponseObject
# ---------------------------------------------------------------------------


class TestFileResponseObject:
    def test_creates_valid_response_object(self):
        from ii_agent.chat.llm.anthropic.provider import FileResponseObject

        obj = FileResponseObject(
            id="file-1",
            provider_file_id="prov-1",
            provider="anthropic",
            content_type="image/png",
            file_name="image.png",
        )
        assert obj.id == "file-1"
        assert obj.provider == "anthropic"

    def test_default_file_size_is_zero(self):
        from ii_agent.chat.llm.anthropic.provider import FileResponseObject

        obj = FileResponseObject(
            id="f1",
            provider_file_id="p1",
            provider="anthropic",
            content_type="text/plain",
            file_name="file.txt",
        )
        assert obj.file_size == 0


# ---------------------------------------------------------------------------
# AnthropicProvider.__init__
# ---------------------------------------------------------------------------


class TestAnthropicProviderInit:
    def test_standard_init(self):
        from ii_agent.chat.llm.anthropic.provider import AnthropicProvider
        import anthropic

        with patch.object(anthropic, "AsyncAnthropic") as mock_client_cls:
            mock_client_cls.return_value = MagicMock()
            config = _make_llm_config()
            provider = AnthropicProvider(config)
            assert provider.model_name == config.model
            assert provider.enable_caching is True

    def test_vertex_init_uses_vertex_client(self):
        from ii_agent.chat.llm.anthropic.provider import AnthropicProvider
        import anthropic

        with patch.object(anthropic, "AsyncAnthropicVertex") as mock_vertex:
            mock_vertex.return_value = MagicMock()
            config = _make_llm_config(
                vertex_project_id="my-project",
                vertex_region="us-east1",
            )
            provider = AnthropicProvider(config)
            mock_vertex.assert_called_once()

    def test_custom_base_url_passed(self):
        from ii_agent.chat.llm.anthropic.provider import AnthropicProvider
        import anthropic

        with patch.object(anthropic, "AsyncAnthropic") as mock_client_cls:
            mock_instance = MagicMock()
            mock_client_cls.return_value = mock_instance
            config = _make_llm_config(base_url="http://custom-api.local")
            provider = AnthropicProvider(config)
            call_kwargs = mock_client_cls.call_args[1]
            assert "base_url" in call_kwargs
            assert call_kwargs["base_url"] == "http://custom-api.local"

    def test_enable_caching_default_true(self):
        from ii_agent.chat.llm.anthropic.provider import AnthropicProvider
        import anthropic

        with patch.object(anthropic, "AsyncAnthropic", return_value=MagicMock()):
            config = _make_llm_config()
            provider = AnthropicProvider(config)
            assert provider.enable_caching is True

    def test_model_method(self):
        from ii_agent.chat.llm.anthropic.provider import AnthropicProvider
        import anthropic

        with patch.object(anthropic, "AsyncAnthropic", return_value=MagicMock()):
            config = _make_llm_config(model="claude-3-5-sonnet-20241022")
            provider = AnthropicProvider(config)
            result = provider.model()
            assert result["id"] == "claude-3-5-sonnet-20241022"
            assert result["name"] == "claude-3-5-sonnet-20241022"


# ---------------------------------------------------------------------------
# _convert_tools
# ---------------------------------------------------------------------------


class TestConvertTools:
    def _make_provider(self):
        from ii_agent.chat.llm.anthropic.provider import AnthropicProvider
        import anthropic

        with patch.object(anthropic, "AsyncAnthropic", return_value=MagicMock()):
            config = _make_llm_config()
            return AnthropicProvider(config)

    def test_returns_none_when_no_tools_no_skills(self):
        provider = self._make_provider()
        result = provider._convert_tools(None, has_skills=False)
        assert result is None

    def test_converts_openai_function_format(self):
        provider = self._make_provider()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = provider._convert_tools(tools)
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "web_search"
        assert "input_schema" in result[0]

    def test_adds_codex_tool_when_has_skills(self):
        from ii_agent.chat.llm.anthropic.provider import CODEX_EXECUTION_TOOL

        provider = self._make_provider()
        result = provider._convert_tools([], has_skills=True)
        assert CODEX_EXECUTION_TOOL in result

    def test_does_not_duplicate_codex_tool(self):
        from ii_agent.chat.llm.anthropic.provider import CODEX_EXECUTION_TOOL

        provider = self._make_provider()
        result = provider._convert_tools([CODEX_EXECUTION_TOOL], has_skills=True)
        assert result.count(CODEX_EXECUTION_TOOL) == 1

    def test_skips_non_function_tools(self):
        provider = self._make_provider()
        tools = [{"type": "builtin", "name": "calculator"}]
        result = provider._convert_tools(tools)
        assert result is None or result == []


# ---------------------------------------------------------------------------
# _validate_inline_image_sizes
# ---------------------------------------------------------------------------


class TestValidateInlineImageSizes:
    def _make_provider(self):
        from ii_agent.chat.llm.anthropic.provider import AnthropicProvider
        import anthropic

        with patch.object(anthropic, "AsyncAnthropic", return_value=MagicMock()):
            config = _make_llm_config()
            return AnthropicProvider(config)

    def test_small_image_does_not_raise(self):
        provider = self._make_provider()
        small_data = b"\xff\xd8\xff" * 100  # ~300 bytes
        msg = Message(
            id=_uuid_mod.uuid4(),
            session_id=_SESSION_ID,
            role=MessageRole.USER,
            parts=[BinaryContent(data=small_data, mime_type="image/jpeg", path="/tmp/img.jpg")],
        )
        provider._validate_inline_image_sizes([msg])  # Should not raise

    def test_oversized_image_raises_error(self):
        from ii_agent.chat.exceptions import AnthropicImageTooLargeError

        provider = self._make_provider()
        large_data = b"\xff" * (5 * 1024 * 1024 + 100)  # > 5MB
        msg = Message(
            id=_uuid_mod.uuid4(),
            session_id=_SESSION_ID,
            role=MessageRole.USER,
            parts=[BinaryContent(data=large_data, mime_type="image/png", path="/tmp/big.png")],
        )
        with pytest.raises(AnthropicImageTooLargeError):
            provider._validate_inline_image_sizes([msg])

    def test_non_image_binary_not_checked(self):
        provider = self._make_provider()
        large_data = b"\x00" * (10 * 1024 * 1024)
        msg = Message(
            id=_uuid_mod.uuid4(),
            session_id=_SESSION_ID,
            role=MessageRole.USER,
            parts=[BinaryContent(data=large_data, mime_type="application/pdf", path="/tmp/big.pdf")],
        )
        provider._validate_inline_image_sizes([msg])  # Should not raise

    def test_empty_messages_no_raise(self):
        provider = self._make_provider()
        provider._validate_inline_image_sizes([])


# ---------------------------------------------------------------------------
# _prepare_request_params
# ---------------------------------------------------------------------------


class TestPrepareRequestParams:
    def _make_provider(self, **kwargs):
        from ii_agent.chat.llm.anthropic.provider import AnthropicProvider
        import anthropic

        with patch.object(anthropic, "AsyncAnthropic", return_value=MagicMock()):
            config = _make_llm_config(**kwargs)
            return AnthropicProvider(config)

    def test_basic_params_have_model_messages_max_tokens(self):
        provider = self._make_provider()
        msgs = [_make_user_message()]
        params, betas = provider._prepare_request_params(msgs)
        assert "model" in params
        assert "messages" in params
        assert "max_tokens" in params

    def test_temperature_added_when_set_and_no_thinking(self):
        # thinking_tokens must be < 1024 to disable extended thinking,
        # which is required for temperature to be included
        provider = self._make_provider(temperature=0.7, thinking_tokens=512)
        msgs = [_make_user_message()]
        params, _ = provider._prepare_request_params(msgs)
        assert params.get("temperature") == 0.7

    def test_temperature_not_added_with_thinking_tokens(self):
        provider = self._make_provider(thinking_tokens=2048)
        msgs = [_make_user_message()]
        params, _ = provider._prepare_request_params(msgs)
        assert "temperature" not in params

    def test_thinking_config_added_when_thinking_tokens_set(self):
        provider = self._make_provider(thinking_tokens=2048)
        msgs = [_make_user_message()]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        params, betas = provider._prepare_request_params(msgs, tools=tools)
        assert "thinking" in params
        assert "interleaved-thinking-2025-05-14" in betas

    def test_tools_converted_and_added(self):
        provider = self._make_provider()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "my_tool",
                    "description": "does stuff",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        params, _ = provider._prepare_request_params([_make_user_message()], tools=tools)
        assert "tools" in params
        assert params["tools"][0]["name"] == "my_tool"

    def test_system_prompt_added_when_present(self):
        provider = self._make_provider()
        msgs = [_make_user_message()]
        params, _ = provider._prepare_request_params(msgs)
        assert "system" in params

    def test_skills_betas_added_when_has_skills(self):
        provider = self._make_provider()
        anthropic_options = {
            "container": {
                "skills": [{"type": "anthropic", "skill_id": "pdf", "version": "latest"}]
            }
        }
        # When has_skills=True, tools must be provided (even empty) to avoid
        # TypeError in _convert_tools (source bug: iterating over None)
        params, betas = provider._prepare_request_params(
            [_make_user_message()],
            tools=[],  # Provide empty list to avoid iteration over None
            anthropic_options=anthropic_options,
        )
        assert "code-execution-2025-08-25" in betas
        assert "skills-2025-10-02" in betas


# ---------------------------------------------------------------------------
# extract_file_ids
# ---------------------------------------------------------------------------


class TestExtractFileIds:
    def test_empty_content_returns_empty_list(self):
        from ii_agent.chat.llm.anthropic.provider import extract_file_ids

        response = MagicMock()
        response.content = []
        result = extract_file_ids(response)
        assert result == []

    def test_bash_code_execution_result_extracts_file_ids(self):
        from ii_agent.chat.llm.anthropic.provider import extract_file_ids

        file_item = MagicMock()
        file_item.file_id = "file_123"

        bash_content = MagicMock()
        bash_content.type = "bash_code_execution_result"
        bash_content.content = [file_item]

        bash_block = MagicMock()
        bash_block.type = "bash_code_execution_tool_result"
        bash_block.content = bash_content

        response = MagicMock()
        response.content = [bash_block]
        result = extract_file_ids(response)
        assert "file_123" in result

    def test_text_editor_result_extracts_file_ids(self):
        from ii_agent.chat.llm.anthropic.provider import extract_file_ids

        file_item = MagicMock()
        file_item.file_id = "file_456"

        editor_content = MagicMock()
        editor_content.type = "text_editor_code_execution_result"
        editor_content.content = [file_item]

        editor_block = MagicMock()
        editor_block.type = "text_editor_code_execution_tool_result"
        editor_block.content = editor_content

        response = MagicMock()
        response.content = [editor_block]
        result = extract_file_ids(response)
        assert "file_456" in result

    def test_deduplicates_file_ids(self):
        from ii_agent.chat.llm.anthropic.provider import extract_file_ids

        file_item1 = MagicMock()
        file_item1.file_id = "dup_file"
        file_item2 = MagicMock()
        file_item2.file_id = "dup_file"

        bash_content = MagicMock()
        bash_content.type = "bash_code_execution_result"
        bash_content.content = [file_item1, file_item2]

        bash_block = MagicMock()
        bash_block.type = "bash_code_execution_tool_result"
        bash_block.content = bash_content

        response = MagicMock()
        response.content = [bash_block]
        result = extract_file_ids(response)
        assert result.count("dup_file") == 1

    def test_items_without_file_id_skipped(self):
        from ii_agent.chat.llm.anthropic.provider import extract_file_ids

        item_no_file = MagicMock(spec=[])  # No file_id attribute

        bash_content = MagicMock()
        bash_content.type = "bash_code_execution_result"
        bash_content.content = [item_no_file]

        bash_block = MagicMock()
        bash_block.type = "bash_code_execution_tool_result"
        bash_block.content = bash_content

        response = MagicMock()
        response.content = [bash_block]
        result = extract_file_ids(response)
        assert result == []

    def test_other_block_types_ignored(self):
        from ii_agent.chat.llm.anthropic.provider import extract_file_ids

        text_block = MagicMock()
        text_block.type = "text"

        response = MagicMock()
        response.content = [text_block]
        result = extract_file_ids(response)
        assert result == []


# ---------------------------------------------------------------------------
# _extract_content_part_from_message
# ---------------------------------------------------------------------------


class TestExtractContentPartFromMessage:
    def _make_provider(self):
        from ii_agent.chat.llm.anthropic.provider import AnthropicProvider
        import anthropic

        with patch.object(anthropic, "AsyncAnthropic", return_value=MagicMock()):
            config = _make_llm_config()
            return AnthropicProvider(config)

    def test_text_block_creates_text_content(self):
        from anthropic.types import TextBlock, Message as AnthropicMessage
        from ii_agent.chat.types import TextContent

        provider = self._make_provider()
        text_block = MagicMock(spec=TextBlock)
        text_block.type = "text"
        text_block.text = "Hello world"

        message = MagicMock()
        message.content = [text_block]

        with patch("ii_agent.chat.llm.anthropic.provider.TextBlock", TextBlock):
            result = provider._extract_content_part_from_message(message)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert result[0].text == "Hello world"

    def test_tool_use_block_creates_tool_call(self):
        from anthropic.types import ToolUseBlock
        from ii_agent.chat.types import ToolCall

        provider = self._make_provider()
        tool_block = MagicMock(spec=ToolUseBlock)
        tool_block.type = "tool_use"
        tool_block.id = "tool_id_1"
        tool_block.name = "web_search"
        tool_block.input = {"query": "hello"}

        message = MagicMock()
        message.content = [tool_block]

        with patch("ii_agent.chat.llm.anthropic.provider.ToolUseBlock", ToolUseBlock):
            result = provider._extract_content_part_from_message(message)

        assert len(result) == 1
        assert isinstance(result[0], ToolCall)
        assert result[0].name == "web_search"

    def test_empty_content_returns_empty_list(self):
        provider = self._make_provider()
        message = MagicMock()
        message.content = []
        result = provider._extract_content_part_from_message(message)
        assert result == []
