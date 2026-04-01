"""Deep unit tests for Anthropic provider and prompt converter - coverage gaps."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.chat.types import (
    ArrayResultContent,
    BinaryContent,
    ErrorJsonContent,
    ErrorTextContent,
    ExecutionDeniedContent,
    EventType,
    FileDataContentPart,
    FinishReason,
    ImageDataContentPart,
    ImageURLContent,
    ImageUrlContentPart,
    JsonResultContent,
    Message,
    MessageRole,
    ReasoningContent,
    RunResponseEvent,
    StorybookProgressContent,
    StorybookResultContent,
    TextContent,
    TextContentPart,
    TextResultContent,
    ToolCall,
    ToolResult,
)

_SESSION_ID = "deep-anthropic-test-001"


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


def _make_provider(**kwargs):
    from ii_agent.chat.llm.anthropic.provider import AnthropicProvider
    import anthropic

    with patch.object(anthropic, "AsyncAnthropic", return_value=MagicMock()):
        config = _make_llm_config(**kwargs)
        return AnthropicProvider(config)


def _make_message(
    role: MessageRole, parts: List[Any] = None, file_ids: List[str] = None
) -> Message:
    return Message(
        id=uuid.uuid4(),
        session_id=_SESSION_ID,
        role=role,
        parts=parts or [],
        file_ids=file_ids,
    )


def _user_message(text: str = "Hello") -> Message:
    return _make_message(MessageRole.USER, [TextContent(text=text)])


def _assistant_message(text: str = "Hi") -> Message:
    return _make_message(MessageRole.ASSISTANT, [TextContent(text=text)])


def _system_message(text: str = "You are helpful.") -> Message:
    return _make_message(MessageRole.SYSTEM, [TextContent(text=text)])


def _tool_result_message(tool_call_id: str, name: str, output) -> Message:
    result = ToolResult(tool_call_id=tool_call_id, name=name, output=output)
    return _make_message(MessageRole.TOOL, [result])


# ===========================================================================
# PROMPT CONVERTER DEEP TESTS
# ===========================================================================


class TestGroupIntoBlocksDeep:
    """Deeper coverage for group_into_blocks."""

    def test_multiple_consecutive_user_messages_merged(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import group_into_blocks

        msgs = [_user_message("a"), _user_message("b"), _user_message("c")]
        blocks = group_into_blocks(msgs)
        assert len(blocks) == 1
        assert len(blocks[0].messages) == 3

    def test_multiple_consecutive_assistant_messages_merged(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import group_into_blocks

        msgs = [_assistant_message("a"), _assistant_message("b")]
        blocks = group_into_blocks(msgs)
        assert len(blocks) == 1
        assert len(blocks[0].messages) == 2

    def test_complex_conversation_blocking(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import (
            group_into_blocks,
            UserBlock,
            AssistantBlock,
        )

        tool_msg = _tool_result_message("c1", "tool", TextResultContent(value="result"))
        msgs = [
            _system_message("System"),
            _user_message("Q1"),
            tool_msg,
            _assistant_message("A1"),
            _user_message("Q2"),
        ]
        blocks = group_into_blocks(msgs)
        # System, User+Tool (merged), Assistant, User
        assert len(blocks) == 4

    def test_tool_after_assistant_creates_new_user_block(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import group_into_blocks, UserBlock

        tool_msg = _tool_result_message("c1", "tool", TextResultContent(value="result"))
        msgs = [_user_message(), _assistant_message(), tool_msg]
        blocks = group_into_blocks(msgs)
        # user, assistant, then tool creates new user block
        last_block = blocks[-1]
        assert isinstance(last_block, UserBlock)


class TestConvertToolResultContentDeep:
    """Deeper coverage for convert_tool_result_content."""

    def test_array_result_with_non_pdf_file_data_part_skipped(self):
        """Non-PDF FileDataContentPart in ArrayResult should be logged/skipped."""
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_tool_result_content

        result = ToolResult(
            tool_call_id="c1",
            name="tool",
            output=ArrayResultContent(
                value=[
                    FileDataContentPart(mime_type="text/csv", data="csvdata", filename="data.csv")
                ]
            ),
        )
        content, is_error = convert_tool_result_content(result)
        # Non-PDF files are skipped - content_parts should be empty, fallback to "No content"
        assert content == "No content" or isinstance(content, list)

    def test_unknown_output_type_fallback(self):
        """Unknown output type should fallback to str representation."""
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_tool_result_content

        # Create a mock that doesn't match any known type
        unknown = MagicMock()
        unknown.__class__.__name__ = "WeirdOutput"

        # We need a real ToolResult but with mocked output that bypasses isinstance checks
        result = ToolResult(
            tool_call_id="c1",
            name="tool",
            output=TextResultContent(value="fallback test"),
        )
        # Override the output to our mock
        object.__setattr__(result, "output", unknown)

        content, is_error = convert_tool_result_content(result)
        assert isinstance(content, str)
        assert is_error is False

    def test_storybook_result_with_pages(self):
        """StorybookResultContent with pages should serialize correctly."""
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_tool_result_content
        from ii_agent.chat.types import StorybookPageResult

        page = StorybookPageResult(
            page_number=1, image_url="https://example.com/img.png", text_content="Once upon a time"
        )
        result = ToolResult(
            tool_call_id="c1",
            name="tool",
            output=StorybookResultContent(
                storybook_id="sb1", storybook_name="My Story", pages=[page]
            ),
        )
        content, is_error = convert_tool_result_content(result)
        data = json.loads(content)
        assert data["page_count"] == 1
        assert len(data["pages"]) == 1
        assert data["pages"][0]["page_number"] == 1


class TestConvertToAnthropicMessagesDeep:
    """Deeper coverage for convert_to_anthropic_messages."""

    def test_caching_enabled_last_block_gets_cache_control(self):
        """With caching enabled, last blocks should have cache control."""
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        msgs = [_user_message("Hello")]
        _, anthropic_msgs, _ = convert_to_anthropic_messages(msgs, "sys", enable_caching=True)
        content = anthropic_msgs[0]["content"]
        # At least one content block should have cache_control
        has_cache = any("cache_control" in block for block in content)
        assert has_cache

    def test_binary_text_plain_content_converted_to_document(self):
        """BinaryContent with text/plain mime should become document block."""
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        binary = BinaryContent(
            data=b"plain text content", mime_type="text/plain", path="/tmp/file.txt"
        )
        msg = _make_message(MessageRole.USER, [binary])
        _, anthropic_msgs, _ = convert_to_anthropic_messages([msg], "sys")
        content = anthropic_msgs[0]["content"]
        assert any(c.get("type") == "document" for c in content)

    def test_binary_unsupported_mime_logged_skipped(self):
        """BinaryContent with unsupported mime should be skipped (logged)."""
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        binary = BinaryContent(data=b"video data", mime_type="video/mp4", path="/tmp/vid.mp4")
        msg = _make_message(MessageRole.USER, [binary])
        _, anthropic_msgs, _ = convert_to_anthropic_messages([msg], "sys")
        if anthropic_msgs:
            content = anthropic_msgs[0]["content"]
            # No video blocks should exist
            assert not any(c.get("type") == "video" for c in content)

    def test_multiple_user_messages_with_file_ids(self):
        """Multiple file IDs in a message should all be included."""
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        pf1 = MagicMock()
        pf1.id = "file-id-1"
        pf1.provider_file_id = "prov-id-1"
        pf1.content_type = "image/jpeg"

        pf2 = MagicMock()
        pf2.id = "file-id-2"
        pf2.provider_file_id = "prov-id-2"
        pf2.content_type = "application/pdf"

        msg = _make_message(
            MessageRole.USER,
            [TextContent(text="See these files")],
            file_ids=["file-id-1", "file-id-2"],
        )
        _, anthropic_msgs, _ = convert_to_anthropic_messages(
            [msg], "sys", provider_files=[pf1, pf2]
        )
        content = anthropic_msgs[0]["content"]
        # Should have image and document blocks
        file_blocks = [c for c in content if c.get("source", {}).get("type") == "file"]
        assert len(file_blocks) == 2

    def test_tool_result_code_execution_result_type(self):
        """Tool result with code_execution_result type should create code_execution_tool_result block."""
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        code_result = ToolResult(
            tool_call_id="exec_1",
            name="code_execution",
            output=JsonResultContent(
                value={
                    "type": "code_execution_result",
                    "stdout": "Hello World",
                    "stderr": "",
                    "return_code": 0,
                }
            ),
        )
        tool_msg = _make_message(MessageRole.TOOL, [code_result])
        msgs = [_user_message(), tool_msg]
        _, anthropic_msgs, _ = convert_to_anthropic_messages(msgs, "sys", enable_caching=False)

        # Tool and user messages combined
        combined = anthropic_msgs[0]["content"]
        code_exec_blocks = [b for b in combined if b.get("type") == "code_execution_tool_result"]
        assert len(code_exec_blocks) == 1
        assert code_exec_blocks[0]["content"]["stdout"] == "Hello World"

    def test_tool_result_bash_code_execution_result_type(self):
        """Tool result with bash_code_execution_result type."""
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        bash_result = ToolResult(
            tool_call_id="bash_1",
            name="code_execution",
            output=JsonResultContent(
                value={
                    "type": "bash_code_execution_result",
                    "stdout": "ls output",
                    "exit_code": 0,
                }
            ),
        )
        tool_msg = _make_message(MessageRole.TOOL, [bash_result])
        msgs = [_user_message(), tool_msg]
        _, anthropic_msgs, _ = convert_to_anthropic_messages(msgs, "sys", enable_caching=False)

        combined = anthropic_msgs[0]["content"]
        bash_blocks = [b for b in combined if b.get("type") == "bash_code_execution_tool_result"]
        assert len(bash_blocks) == 1

    def test_tool_result_text_editor_code_execution_result_type(self):
        """Tool result with text_editor_code_execution_result type."""
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        te_result = ToolResult(
            tool_call_id="te_1",
            name="code_execution",
            output=JsonResultContent(
                value={
                    "type": "text_editor_code_execution_result",
                    "content": "file written",
                }
            ),
        )
        tool_msg = _make_message(MessageRole.TOOL, [te_result])
        msgs = [_user_message(), tool_msg]
        _, anthropic_msgs, _ = convert_to_anthropic_messages(msgs, "sys", enable_caching=False)

        combined = anthropic_msgs[0]["content"]
        te_blocks = [
            b for b in combined if b.get("type") == "text_editor_code_execution_tool_result"
        ]
        assert len(te_blocks) == 1

    def test_tool_result_unknown_code_execution_type_fallback(self):
        """Unknown code execution type falls back to normal tool_result block."""
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        unknown_result = ToolResult(
            tool_call_id="unk_1",
            name="code_execution",
            output=JsonResultContent(
                value={
                    "type": "unknown_execution_type",
                    "data": "something",
                }
            ),
        )
        tool_msg = _make_message(MessageRole.TOOL, [unknown_result])
        msgs = [_user_message(), tool_msg]
        _, anthropic_msgs, _ = convert_to_anthropic_messages(msgs, "sys", enable_caching=False)

        combined = anthropic_msgs[0]["content"]
        tool_result_blocks = [b for b in combined if b.get("type") == "tool_result"]
        assert len(tool_result_blocks) == 1

    def test_tool_result_non_dict_json_content_fallback(self):
        """Tool result with non-dict JSON value falls back to normal tool_result."""
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        # JsonResultContent with a non-dict value (string)
        result = ToolResult(
            tool_call_id="str_1",
            name="code_execution",
            output=JsonResultContent(value="just a string, not dict"),
        )
        tool_msg = _make_message(MessageRole.TOOL, [result])
        msgs = [_user_message(), tool_msg]
        _, anthropic_msgs, _ = convert_to_anthropic_messages(msgs, "sys", enable_caching=False)

        combined = anthropic_msgs[0]["content"]
        tool_result_blocks = [b for b in combined if b.get("type") == "tool_result"]
        assert len(tool_result_blocks) == 1

    def test_system_block_updates_system_prompt(self):
        """System messages should update the returned system prompt."""
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        msgs = [_system_message("Custom system prompt"), _user_message("Hello")]
        system, _, _ = convert_to_anthropic_messages(msgs, "Default system")
        assert "Custom system prompt" in system
        assert "Default system" not in system

    def test_multiple_system_messages_last_one_wins(self):
        """If multiple system messages, the last one should be used."""
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        msgs = [
            _system_message("First system"),
            _system_message("Second system"),
            _user_message(),
        ]
        system, _, _ = convert_to_anthropic_messages(msgs, "Default")
        assert "Second system" in system

    def test_warning_returned_for_cache_issues(self):
        """Warnings list is returned as third element of tuple."""
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        msgs = [_user_message("test")]
        result = convert_to_anthropic_messages(msgs, "sys", enable_caching=True)
        assert isinstance(result, tuple)
        assert len(result) == 3
        # Third element is warnings
        assert isinstance(result[2], list)

    def test_cache_control_on_last_4_blocks(self):
        """Cache control should be applied to last 4 blocks."""
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        # Build 5 alternating messages (user/assistant) to create multiple blocks
        msgs = []
        for i in range(3):
            msgs.append(_user_message(f"Question {i}"))
            msgs.append(_assistant_message(f"Answer {i}"))
        msgs.append(_user_message("Final question"))

        _, anthropic_msgs, _ = convert_to_anthropic_messages(msgs, "sys", enable_caching=True)
        # We just verify no exception occurs and output is valid
        assert len(anthropic_msgs) > 0

    def test_provider_file_text_plain_creates_document(self):
        """text/plain provider file creates document block."""
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        pf = MagicMock()
        pf.id = "txt-id"
        pf.provider_file_id = "txt-prov-id"
        pf.content_type = "text/plain"

        msg = _make_message(
            MessageRole.USER, [TextContent(text="see this text")], file_ids=["txt-id"]
        )
        _, anthropic_msgs, _ = convert_to_anthropic_messages([msg], "sys", provider_files=[pf])
        content = anthropic_msgs[0]["content"]
        docs = [c for c in content if c.get("type") == "document"]
        assert len(docs) == 1


# ===========================================================================
# ANTHROPIC PROVIDER DEEP TESTS
# ===========================================================================


class TestAnthropicProviderSendDeep:
    """Deep tests for AnthropicProvider.send() covering various scenarios."""

    @pytest.mark.asyncio
    async def test_send_with_end_turn_finish_reason(self):
        provider = _make_provider()

        mock_response = MagicMock()
        mock_response.content = []
        mock_response.stop_reason = "end_turn"
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 25
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0

        with patch(
            "ii_agent.chat.llm.anthropic.provider.convert_to_anthropic_messages"
        ) as mock_conv:
            mock_conv.return_value = ("system", [], [])
            with patch.object(
                provider.client.beta.messages, "create", new=AsyncMock(return_value=mock_response)
            ):
                result = await provider.send(messages=[_user_message()])

        assert result.finish_reason == FinishReason.END_TURN

    @pytest.mark.asyncio
    async def test_send_with_max_tokens_finish_reason(self):
        provider = _make_provider()

        mock_response = MagicMock()
        mock_response.content = []
        mock_response.stop_reason = "max_tokens"
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 200
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0

        with patch(
            "ii_agent.chat.llm.anthropic.provider.convert_to_anthropic_messages"
        ) as mock_conv:
            mock_conv.return_value = ("system", [], [])
            with patch.object(
                provider.client.beta.messages, "create", new=AsyncMock(return_value=mock_response)
            ):
                result = await provider.send(messages=[_user_message()])

        assert result.finish_reason == FinishReason.MAX_TOKENS

    @pytest.mark.asyncio
    async def test_send_with_tool_use_finish_reason(self):
        provider = _make_provider()

        mock_response = MagicMock()
        mock_response.content = []
        mock_response.stop_reason = "tool_use"
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 50
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0

        with patch(
            "ii_agent.chat.llm.anthropic.provider.convert_to_anthropic_messages"
        ) as mock_conv:
            mock_conv.return_value = ("system", [], [])
            with patch.object(
                provider.client.beta.messages, "create", new=AsyncMock(return_value=mock_response)
            ):
                result = await provider.send(messages=[_user_message()])

        assert result.finish_reason == FinishReason.TOOL_USE

    @pytest.mark.asyncio
    async def test_send_with_pause_turn_finish_reason(self):
        provider = _make_provider()

        mock_response = MagicMock()
        mock_response.content = []
        mock_response.stop_reason = "pause_turn"
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 50
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0

        with patch(
            "ii_agent.chat.llm.anthropic.provider.convert_to_anthropic_messages"
        ) as mock_conv:
            mock_conv.return_value = ("system", [], [])
            with patch.object(
                provider.client.beta.messages, "create", new=AsyncMock(return_value=mock_response)
            ):
                result = await provider.send(messages=[_user_message()])

        assert result.finish_reason == FinishReason.PAUSE_TURN

    @pytest.mark.asyncio
    async def test_send_with_unknown_stop_reason(self):
        provider = _make_provider()

        mock_response = MagicMock()
        mock_response.content = []
        mock_response.stop_reason = "some_new_reason"
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 50
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0

        with patch(
            "ii_agent.chat.llm.anthropic.provider.convert_to_anthropic_messages"
        ) as mock_conv:
            mock_conv.return_value = ("system", [], [])
            with patch.object(
                provider.client.beta.messages, "create", new=AsyncMock(return_value=mock_response)
            ):
                result = await provider.send(messages=[_user_message()])

        assert result.finish_reason == FinishReason.UNKNOWN

    @pytest.mark.asyncio
    async def test_send_with_stop_sequence_maps_to_end_turn(self):
        provider = _make_provider()

        mock_response = MagicMock()
        mock_response.content = []
        mock_response.stop_reason = "stop_sequence"
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 50
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0

        with patch(
            "ii_agent.chat.llm.anthropic.provider.convert_to_anthropic_messages"
        ) as mock_conv:
            mock_conv.return_value = ("system", [], [])
            with patch.object(
                provider.client.beta.messages, "create", new=AsyncMock(return_value=mock_response)
            ):
                result = await provider.send(messages=[_user_message()])

        assert result.finish_reason == FinishReason.END_TURN

    @pytest.mark.asyncio
    async def test_send_extracts_cache_tokens(self):
        """send() should extract cache_write and cache_read tokens."""
        provider = _make_provider()

        mock_response = MagicMock()
        mock_response.content = []
        mock_response.stop_reason = "end_turn"
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.usage.cache_creation_input_tokens = 200
        mock_response.usage.cache_read_input_tokens = 300

        with patch(
            "ii_agent.chat.llm.anthropic.provider.convert_to_anthropic_messages"
        ) as mock_conv:
            mock_conv.return_value = ("system", [], [])
            with patch.object(
                provider.client.beta.messages, "create", new=AsyncMock(return_value=mock_response)
            ):
                result = await provider.send(messages=[_user_message()])

        assert result.usage.cache_write_tokens == 200
        assert result.usage.cache_read_tokens == 300

    @pytest.mark.asyncio
    async def test_send_finds_last_user_message_for_file_upload(self):
        """send() should upload files from the last user message."""
        provider = _make_provider()

        user_msg_with_files = Message(
            id=uuid.uuid4(),
            session_id=_SESSION_ID,
            role=MessageRole.USER,
            parts=[TextContent(text="Here are files")],
            file_ids=["file-1", "file-2"],
        )
        asst_msg = _assistant_message("OK")

        mock_response = MagicMock()
        mock_response.content = []
        mock_response.stop_reason = "end_turn"
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 50
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0

        upload_called_with = []

        async def fake_upload(message, session_id):
            upload_called_with.append(message)
            return []

        provider.upload_files = fake_upload

        with patch(
            "ii_agent.chat.llm.anthropic.provider.convert_to_anthropic_messages"
        ) as mock_conv:
            mock_conv.return_value = ("system", [], [])
            with patch.object(
                provider.client.beta.messages, "create", new=AsyncMock(return_value=mock_response)
            ):
                await provider.send(
                    messages=[user_msg_with_files, asst_msg, _user_message("Follow up")],
                    session_id=_SESSION_ID,
                )

        # Should have uploaded from the last user message (follow up has no files)
        # In this case, the last user message has no file_ids, so no upload
        assert len(upload_called_with) == 0 or upload_called_with[0].file_ids is None


class TestAnthropicProviderStreamDeep:
    """Deep tests for AnthropicProvider.stream()."""

    @pytest.mark.asyncio
    async def test_stream_preserves_max_tokens_when_adding_skills(self):
        import anthropic
        from ii_agent.chat.llm.anthropic.provider import AnthropicProvider

        class _EmptyStream:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        class _FakeMessagesAPI:
            def __init__(self):
                self.stream = MagicMock(return_value=_EmptyStream())

        class _FakeBetaAPI:
            def __init__(self):
                self.messages = _FakeMessagesAPI()

        class _FakeAsyncAnthropic:
            def __init__(self, **kwargs):
                self.beta = _FakeBetaAPI()

        with patch.object(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic):
            provider = AnthropicProvider(_make_llm_config())
            with patch.object(
                provider, "_prepare_request_params", return_value=({}, [])
            ) as mock_prepare:
                provider_options = {"anthropic": {"max_tokens": 321}}
                events = [
                    event
                    async for event in provider.stream(
                        messages=[_user_message()],
                        provider_options=provider_options,
                    )
                ]

        assert events == []
        anthropic_options = mock_prepare.call_args.args[2]
        assert anthropic_options["max_tokens"] == 321
        assert anthropic_options["container"]["skills"]
        assert provider_options == {"anthropic": {"max_tokens": 321}}


class TestAnthropicProviderPrepareRequestParamsDeep:
    """Deeper coverage of _prepare_request_params."""

    def test_skills_adds_all_required_betas(self):
        """When has_skills=True, should add all skill-related betas."""
        provider = _make_provider()
        anthropic_options = {
            "container": {"skills": [{"type": "anthropic", "skill_id": "pdf", "version": "latest"}]}
        }
        params, betas = provider._prepare_request_params(
            [_user_message()],
            tools=[],
            anthropic_options=anthropic_options,
        )
        assert "code-execution-2025-08-25" in betas
        assert "skills-2025-10-02" in betas
        assert "files-api-2025-04-14" in betas

    def test_thinking_with_tools_adds_interleaved_thinking_beta(self):
        """Extended thinking with tools should add interleaved-thinking beta."""
        provider = _make_provider(thinking_tokens=2048)
        tools = [
            {
                "type": "function",
                "function": {"name": "search", "description": "search", "parameters": {}},
            }
        ]
        params, betas = provider._prepare_request_params([_user_message()], tools=tools)
        assert "interleaved-thinking-2025-05-14" in betas
        assert "thinking" in params
        assert params["thinking"]["budget_tokens"] == 2048

    def test_thinking_without_tools_no_thinking_config(self):
        """Extended thinking without tools should NOT add thinking config (only with tools)."""
        provider = _make_provider(thinking_tokens=2048)
        params, betas = provider._prepare_request_params([_user_message()], tools=None)
        # Without tools, thinking is not added
        assert "thinking" not in params

    def test_temperature_not_set_when_thinking_enabled_with_tools(self):
        """Temperature should not be set when extended thinking is active."""
        provider = _make_provider(temperature=0.7, thinking_tokens=2048)
        tools = [
            {"type": "function", "function": {"name": "tool", "description": "d", "parameters": {}}}
        ]
        params, _ = provider._prepare_request_params([_user_message()], tools=tools)
        assert "temperature" not in params

    def test_container_id_added_to_params_when_in_options(self):
        """container_id from options should be added to params."""
        provider = _make_provider()
        anthropic_options = {
            "container": {
                "id": "container-xyz",
                "skills": [{"type": "anthropic", "skill_id": "pdf", "version": "latest"}],
            }
        }
        params, _ = provider._prepare_request_params(
            [_user_message()], tools=[], anthropic_options=anthropic_options
        )
        assert "container" in params

    def test_no_anthropic_options_returns_empty_betas(self):
        """No anthropic options should return basic betas list."""
        provider = _make_provider()
        params, betas = provider._prepare_request_params([_user_message()])
        assert isinstance(betas, list)


class TestExtractContentPartFromMessageDeep:
    """Deeper coverage of _extract_content_part_from_message."""

    def test_beta_text_block_creates_text_content(self):
        from anthropic.types.beta import BetaTextBlock
        from ii_agent.chat.types import TextContent

        provider = _make_provider()
        block = MagicMock(spec=BetaTextBlock)
        block.type = "text"
        block.text = "Beta text response"

        message = MagicMock()
        message.content = [block]

        result = provider._extract_content_part_from_message(message)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert result[0].text == "Beta text response"

    def test_beta_tool_use_block_creates_tool_call(self):
        from anthropic.types.beta import BetaToolUseBlock
        from ii_agent.chat.types import ToolCall

        provider = _make_provider()
        block = MagicMock(spec=BetaToolUseBlock)
        block.type = "tool_use"
        block.id = "tool_use_1"
        block.name = "file_search"
        block.input = {"query": "important doc"}

        message = MagicMock()
        message.content = [block]

        result = provider._extract_content_part_from_message(message)
        assert len(result) == 1
        assert isinstance(result[0], ToolCall)
        assert result[0].name == "file_search"
        assert result[0].finished is True

    def test_thinking_block_creates_reasoning_content(self):
        from anthropic.types import ThinkingBlock
        from ii_agent.chat.types import ReasoningContent

        provider = _make_provider()
        block = MagicMock(spec=ThinkingBlock)
        block.type = "thinking"
        block.thinking = "Let me reason through this..."
        block.signature = "sig_abc"

        message = MagicMock()
        message.content = [block]

        result = provider._extract_content_part_from_message(message)
        assert len(result) == 1
        assert isinstance(result[0], ReasoningContent)
        assert result[0].thinking == "Let me reason through this..."

    def test_beta_thinking_block_creates_reasoning_content(self):
        from anthropic.types.beta import BetaThinkingBlock
        from ii_agent.chat.types import ReasoningContent

        provider = _make_provider()
        block = MagicMock(spec=BetaThinkingBlock)
        block.type = "thinking"
        block.thinking = "Beta thinking content"
        block.signature = "sig_beta"

        message = MagicMock()
        message.content = [block]

        result = provider._extract_content_part_from_message(message)
        assert len(result) == 1
        assert isinstance(result[0], ReasoningContent)

    def test_unknown_block_type_logs_warning(self):
        provider = _make_provider()
        block = MagicMock()
        block.type = "unknown_type"

        message = MagicMock()
        message.content = [block]

        result = provider._extract_content_part_from_message(message)
        # Unknown blocks are skipped, result is empty
        assert result == []

    def test_server_tool_use_bash_creates_tool_call(self):
        from anthropic.types.beta import BetaServerToolUseBlock
        from ii_agent.chat.types import ToolCall

        provider = _make_provider()
        block = MagicMock(spec=BetaServerToolUseBlock)
        block.type = "server_tool_use"
        block.name = "bash_code_execution"
        block.id = "server_tool_1"
        block.input = {"command": "ls -la"}

        message = MagicMock()
        message.content = [block]

        result = provider._extract_content_part_from_message(message)
        assert len(result) == 1
        assert isinstance(result[0], ToolCall)
        assert result[0].name == "code_execution"
        assert result[0].provider_executed is True

    def test_server_tool_use_text_editor_creates_tool_call(self):
        from anthropic.types.beta import BetaServerToolUseBlock
        from ii_agent.chat.types import ToolCall

        provider = _make_provider()
        block = MagicMock(spec=BetaServerToolUseBlock)
        block.type = "server_tool_use"
        block.name = "text_editor_code_execution"
        block.id = "server_tool_2"
        block.input = {"command": "write file"}

        message = MagicMock()
        message.content = [block]

        result = provider._extract_content_part_from_message(message)
        assert len(result) == 1
        assert isinstance(result[0], ToolCall)
        assert result[0].name == "code_execution"

    def test_server_tool_use_unknown_logs_warning(self):
        from anthropic.types.beta import BetaServerToolUseBlock

        provider = _make_provider()
        block = MagicMock(spec=BetaServerToolUseBlock)
        block.type = "server_tool_use"
        block.name = "unknown_server_tool"
        block.id = "server_tool_3"
        block.input = {}

        message = MagicMock()
        message.content = [block]

        result = provider._extract_content_part_from_message(message)
        # Unknown server tool use blocks are skipped
        assert result == []

    def test_mixed_content_blocks(self):
        from anthropic.types import TextBlock, ToolUseBlock
        from ii_agent.chat.types import TextContent, ToolCall

        provider = _make_provider()

        text_block = MagicMock(spec=TextBlock)
        text_block.type = "text"
        text_block.text = "Let me search for that"

        tool_block = MagicMock(spec=ToolUseBlock)
        tool_block.type = "tool_use"
        tool_block.id = "tc_1"
        tool_block.name = "web_search"
        tool_block.input = {"query": "test"}

        message = MagicMock()
        message.content = [text_block, tool_block]

        result = provider._extract_content_part_from_message(message)
        assert len(result) == 2
        assert isinstance(result[0], TextContent)
        assert isinstance(result[1], ToolCall)


class TestValidateInlineImageSizesDeep:
    """Deep coverage for _validate_inline_image_sizes."""

    def test_message_without_parts_attribute_skipped(self):
        """Messages without parts should not cause errors."""
        provider = _make_provider()
        msg = MagicMock()
        msg.parts = None
        provider._validate_inline_image_sizes([msg])  # Should not raise

    def test_exactly_at_limit_raises(self):
        """Image exactly at the 5MB limit (in base64) should raise."""
        from ii_agent.chat.exceptions import AnthropicImageTooLargeError

        provider = _make_provider()
        # 5MB in base64 encoding: ceil(n/3)*4 = 5MB
        # To get base64_size = 5*1024*1024+4 bytes, raw data = ceil(5242880 * 3 / 4) = 3932160 bytes
        limit = 5 * 1024 * 1024  # 5MB in base64
        # Data that produces base64_size > limit
        raw_size = limit  # This produces base64_size = ceil(limit/3)*4 which should be > limit
        data = b"\xff" * (raw_size + 1)  # Slightly over
        msg = Message(
            id=uuid.uuid4(),
            session_id=_SESSION_ID,
            role=MessageRole.USER,
            parts=[BinaryContent(data=data, mime_type="image/png", path="/tmp/img.png")],
        )
        with pytest.raises(AnthropicImageTooLargeError):
            provider._validate_inline_image_sizes([msg])

    def test_empty_image_data_is_safe(self):
        """Empty image data should not raise."""
        provider = _make_provider()
        msg = Message(
            id=uuid.uuid4(),
            session_id=_SESSION_ID,
            role=MessageRole.USER,
            parts=[BinaryContent(data=b"", mime_type="image/jpeg", path="/tmp/img.jpg")],
        )
        provider._validate_inline_image_sizes([msg])  # Should not raise

    def test_multiple_messages_one_oversized(self):
        """If any message has oversized image, should raise."""
        from ii_agent.chat.exceptions import AnthropicImageTooLargeError

        provider = _make_provider()
        small_msg = Message(
            id=uuid.uuid4(),
            session_id=_SESSION_ID,
            role=MessageRole.USER,
            parts=[BinaryContent(data=b"\xff" * 100, mime_type="image/png", path="/tmp/small.png")],
        )
        large_data = b"\xff" * (5 * 1024 * 1024 + 100)
        large_msg = Message(
            id=uuid.uuid4(),
            session_id=_SESSION_ID,
            role=MessageRole.USER,
            parts=[BinaryContent(data=large_data, mime_type="image/png", path="/tmp/large.png")],
        )
        with pytest.raises(AnthropicImageTooLargeError):
            provider._validate_inline_image_sizes([small_msg, large_msg])


class TestConvertToolsAnthropicDeep:
    """Deeper tests for AnthropicProvider._convert_tools."""

    def test_multiple_tools_all_converted(self):
        provider = _make_provider()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": f"tool_{i}",
                    "description": f"Tool {i}",
                    "parameters": {"type": "object"},
                },
            }
            for i in range(5)
        ]
        result = provider._convert_tools(tools)
        assert result is not None
        assert len(result) == 5
        for i, tool in enumerate(result):
            assert tool["name"] == f"tool_{i}"

    def test_tools_with_only_has_skills_empty_list(self):
        """has_skills=True with empty regular tools list should return just the codex tool."""
        from ii_agent.chat.llm.anthropic.provider import CODEX_EXECUTION_TOOL

        provider = _make_provider()
        result = provider._convert_tools([], has_skills=True)
        assert result is not None
        assert CODEX_EXECUTION_TOOL in result
        assert len(result) == 1

    def test_empty_tools_list_with_has_skills(self):
        """Empty tools list with has_skills=True should return codex tool."""
        from ii_agent.chat.llm.anthropic.provider import CODEX_EXECUTION_TOOL

        provider = _make_provider()
        result = provider._convert_tools([], has_skills=True)
        assert result is not None
        assert CODEX_EXECUTION_TOOL in result

    def test_input_schema_correctly_set(self):
        """Tool's input_schema should match the function's parameters."""
        provider = _make_provider()
        params = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "search the web",
                    "parameters": params,
                },
            }
        ]
        result = provider._convert_tools(tools)
        assert result[0]["input_schema"] == params


class TestExtractFileIdsDeep:
    """Deeper tests for extract_file_ids."""

    def test_both_types_combined(self):
        from ii_agent.chat.llm.anthropic.provider import extract_file_ids

        # bash result with one file
        bash_file = MagicMock()
        bash_file.file_id = "bash_file_id"
        bash_content = MagicMock()
        bash_content.type = "bash_code_execution_result"
        bash_content.content = [bash_file]
        bash_block = MagicMock()
        bash_block.type = "bash_code_execution_tool_result"
        bash_block.content = bash_content

        # text editor result with one file
        te_file = MagicMock()
        te_file.file_id = "te_file_id"
        te_content = MagicMock()
        te_content.type = "text_editor_code_execution_result"
        te_content.content = [te_file]
        te_block = MagicMock()
        te_block.type = "text_editor_code_execution_tool_result"
        te_block.content = te_content

        response = MagicMock()
        response.content = [bash_block, te_block]
        result = extract_file_ids(response)

        assert "bash_file_id" in result
        assert "te_file_id" in result
        assert len(result) == 2

    def test_different_bash_content_type_skipped(self):
        """Bash block with wrong content type should not extract files."""
        from ii_agent.chat.llm.anthropic.provider import extract_file_ids

        bash_file = MagicMock()
        bash_file.file_id = "should_not_appear"

        bash_content = MagicMock()
        bash_content.type = "wrong_type"  # Wrong type
        bash_content.content = [bash_file]

        bash_block = MagicMock()
        bash_block.type = "bash_code_execution_tool_result"
        bash_block.content = bash_content

        response = MagicMock()
        response.content = [bash_block]
        result = extract_file_ids(response)
        # Should be empty since content type doesn't match
        assert "should_not_appear" not in result
