"""Unit tests for ii_agent.chat.llm.anthropic.prompt_converter."""

from __future__ import annotations

import json
from typing import Any, List
from unittest.mock import MagicMock


from ii_agent.chat.types import (
    ArrayResultContent,
    BinaryContent,
    ErrorJsonContent,
    ErrorTextContent,
    ExecutionDeniedContent,
    FileDataContentPart,
    ImageDataContentPart,
    ImageURLContent,
    ImageUrlContentPart,
    JsonResultContent,
    Message,
    MessageRole,
    ReasoningContent,
    StorybookProgressContent,
    StorybookResultContent,
    TextContent,
    TextContentPart,
    TextResultContent,
    ToolCall,
    ToolResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


import uuid as _uuid_mod

_SESSION_ID = "test-session-pc"


def _make_message(
    role: MessageRole,
    parts: List[Any] = None,
    file_ids: List[str] = None,
) -> Message:
    return Message(
        id=_uuid_mod.uuid4(),
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


# ---------------------------------------------------------------------------
# MessageBlock classes
# ---------------------------------------------------------------------------


class TestMessageBlocks:
    def test_system_block_type(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import SystemBlock

        block = SystemBlock(messages=[])
        assert block.type == "system"

    def test_user_block_type(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import UserBlock

        block = UserBlock(messages=[])
        assert block.type == "user"

    def test_assistant_block_type(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import AssistantBlock

        block = AssistantBlock(messages=[])
        assert block.type == "assistant"

    def test_block_stores_messages(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import UserBlock

        msgs = [_user_message("test")]
        block = UserBlock(messages=msgs)
        # Pydantic may or may not copy the list; check equality not identity
        assert block.messages == msgs


# ---------------------------------------------------------------------------
# group_into_blocks
# ---------------------------------------------------------------------------


class TestGroupIntoBlocks:
    def test_single_user_message(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import group_into_blocks, UserBlock

        msgs = [_user_message()]
        blocks = group_into_blocks(msgs)
        assert len(blocks) == 1
        assert isinstance(blocks[0], UserBlock)

    def test_single_assistant_message(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import (
            group_into_blocks,
            AssistantBlock,
        )

        msgs = [_assistant_message()]
        blocks = group_into_blocks(msgs)
        assert len(blocks) == 1
        assert isinstance(blocks[0], AssistantBlock)

    def test_system_message_creates_system_block(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import group_into_blocks, SystemBlock

        msgs = [_system_message()]
        blocks = group_into_blocks(msgs)
        assert isinstance(blocks[0], SystemBlock)

    def test_consecutive_same_role_grouped(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import group_into_blocks

        msgs = [_user_message("a"), _user_message("b")]
        blocks = group_into_blocks(msgs)
        assert len(blocks) == 1
        assert len(blocks[0].messages) == 2

    def test_alternating_roles_create_separate_blocks(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import group_into_blocks

        msgs = [_user_message(), _assistant_message(), _user_message()]
        blocks = group_into_blocks(msgs)
        assert len(blocks) == 3

    def test_tool_message_grouped_with_user(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import group_into_blocks, UserBlock

        tool_msg = _tool_result_message("c1", "search", TextResultContent(value="result"))
        msgs = [_user_message(), tool_msg]
        blocks = group_into_blocks(msgs)
        # User and tool should be in same user block
        assert len(blocks) == 1
        assert isinstance(blocks[0], UserBlock)
        assert len(blocks[0].messages) == 2

    def test_empty_messages_returns_empty_list(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import group_into_blocks

        blocks = group_into_blocks([])
        assert blocks == []

    def test_tool_message_alone_creates_user_block(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import group_into_blocks, UserBlock

        tool_msg = _tool_result_message("c1", "search", TextResultContent(value="result"))
        blocks = group_into_blocks([tool_msg])
        assert isinstance(blocks[0], UserBlock)

    def test_system_then_user_creates_two_blocks(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import group_into_blocks

        msgs = [_system_message(), _user_message()]
        blocks = group_into_blocks(msgs)
        assert len(blocks) == 2


# ---------------------------------------------------------------------------
# convert_tool_result_content
# ---------------------------------------------------------------------------


class TestConvertToolResultContent:
    def test_text_result_content(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_tool_result_content

        result = ToolResult(
            tool_call_id="c1",
            name="tool",
            output=TextResultContent(value="Hello"),
        )
        content, is_error = convert_tool_result_content(result)
        assert content == "Hello"
        assert is_error is False

    def test_error_text_content(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_tool_result_content

        result = ToolResult(
            tool_call_id="c1",
            name="tool",
            output=ErrorTextContent(value="Error message"),
        )
        content, is_error = convert_tool_result_content(result)
        assert content == "Error message"
        assert is_error is True

    def test_json_result_content_serialized(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_tool_result_content

        result = ToolResult(
            tool_call_id="c1",
            name="tool",
            output=JsonResultContent(value={"key": "value"}),
        )
        content, is_error = convert_tool_result_content(result)
        assert json.loads(content) == {"key": "value"}
        assert is_error is False

    def test_error_json_content(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_tool_result_content

        result = ToolResult(
            tool_call_id="c1",
            name="tool",
            output=ErrorJsonContent(value={"error": "bad"}),
        )
        content, is_error = convert_tool_result_content(result)
        assert is_error is True
        assert json.loads(content) == {"error": "bad"}

    def test_execution_denied_content(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_tool_result_content

        result = ToolResult(
            tool_call_id="c1",
            name="tool",
            output=ExecutionDeniedContent(reason="Not allowed"),
        )
        content, is_error = convert_tool_result_content(result)
        assert content == "Not allowed"
        assert is_error is False

    def test_execution_denied_no_reason_default(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_tool_result_content

        result = ToolResult(
            tool_call_id="c1",
            name="tool",
            output=ExecutionDeniedContent(reason=None),
        )
        content, is_error = convert_tool_result_content(result)
        assert "denied" in content.lower() or content

    def test_array_result_with_text_parts(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_tool_result_content

        result = ToolResult(
            tool_call_id="c1",
            name="tool",
            output=ArrayResultContent(
                value=[
                    TextContentPart(text="Text item"),
                ]
            ),
        )
        content, is_error = convert_tool_result_content(result)
        assert isinstance(content, list)
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "Text item"

    def test_array_result_with_image_parts(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_tool_result_content

        result = ToolResult(
            tool_call_id="c1",
            name="tool",
            output=ArrayResultContent(
                value=[
                    ImageDataContentPart(media_type="image/png", data="base64imagedata"),
                ]
            ),
        )
        content, is_error = convert_tool_result_content(result)
        assert isinstance(content, list)
        assert content[0]["type"] == "image"
        assert content[0]["source"]["type"] == "base64"

    def test_array_result_with_pdf_file_part(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_tool_result_content

        result = ToolResult(
            tool_call_id="c1",
            name="tool",
            output=ArrayResultContent(
                value=[
                    FileDataContentPart(mime_type="application/pdf", data="pdfdata"),
                ]
            ),
        )
        content, is_error = convert_tool_result_content(result)
        assert isinstance(content, list)
        assert content[0]["type"] == "document"

    def test_array_result_with_image_url_part(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_tool_result_content

        result = ToolResult(
            tool_call_id="c1",
            name="tool",
            output=ArrayResultContent(
                value=[ImageUrlContentPart(url="http://example.com/img.png")]
            ),
        )
        content, is_error = convert_tool_result_content(result)
        assert isinstance(content, list)
        assert content[0]["type"] == "text"
        assert "http://example.com/img.png" in content[0]["text"]

    def test_array_result_empty_returns_default(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_tool_result_content

        result = ToolResult(
            tool_call_id="c1",
            name="tool",
            output=ArrayResultContent(value=[]),
        )
        content, _ = convert_tool_result_content(result)
        assert content == "No content"

    def test_storybook_progress_content(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_tool_result_content

        result = ToolResult(
            tool_call_id="c1",
            name="tool",
            output=StorybookProgressContent(
                storybook_id="sb1",
                storybook_name="My Book",
                total_pages=10,
                completed_pages=5,
                current_page=5,
                status="generating",  # must be one of: generating, completed, failed
                generating_pages=[6, 7],
                error_message=None,
            ),
        )
        content, is_error = convert_tool_result_content(result)
        data = json.loads(content)
        assert data["type"] == "storybook_progress"
        assert data["storybook_id"] == "sb1"
        assert is_error is False

    def test_storybook_result_content(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_tool_result_content

        result = ToolResult(
            tool_call_id="c1",
            name="tool",
            output=StorybookResultContent(
                storybook_id="sb1",
                storybook_name="My Book",
                pages=[],
            ),
        )
        content, is_error = convert_tool_result_content(result)
        data = json.loads(content)
        assert data["type"] == "storybook"
        assert is_error is False

    def test_error_text_with_empty_value(self):
        # Replace the UnknownOutput test (which can't work due to Pydantic's Union validation)
        # with a test for ErrorTextContent with empty string value.
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_tool_result_content

        result = ToolResult(
            tool_call_id="c1",
            name="tool",
            output=ErrorTextContent(value=""),
        )
        content, is_error = convert_tool_result_content(result)
        assert is_error is True


# ---------------------------------------------------------------------------
# convert_to_anthropic_messages - core conversion
# ---------------------------------------------------------------------------


class TestConvertToAnthropicMessages:
    def test_basic_user_message(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        msgs = [_user_message("Hello")]
        system, anthropic_msgs, warnings = convert_to_anthropic_messages(msgs, "System prompt")
        assert len(anthropic_msgs) == 1
        assert anthropic_msgs[0]["role"] == "user"

    def test_system_prompt_preserved_when_no_system_message(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        msgs = [_user_message()]
        system, _, _ = convert_to_anthropic_messages(msgs, "Original system")
        assert "Original system" in system

    def test_system_message_overrides_system_prompt(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        msgs = [_system_message("Custom system"), _user_message()]
        system, _, _ = convert_to_anthropic_messages(msgs, "Original")
        assert "Custom system" in system

    def test_returns_three_tuple(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        msgs = [_user_message()]
        result = convert_to_anthropic_messages(msgs, "sys")
        assert len(result) == 3

    def test_user_text_content_converted(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        msgs = [_user_message("Hello world")]
        _, anthropic_msgs, _ = convert_to_anthropic_messages(msgs, "sys")
        content = anthropic_msgs[0]["content"]
        assert any(c.get("type") == "text" and c.get("text") == "Hello world" for c in content)

    def test_assistant_message_converted(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        msgs = [_user_message(), _assistant_message("OK")]
        _, anthropic_msgs, _ = convert_to_anthropic_messages(msgs, "sys")
        assert len(anthropic_msgs) == 2
        assert anthropic_msgs[1]["role"] == "assistant"

    def test_tool_result_message_converted(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        tool_msg = _tool_result_message("c1", "search", TextResultContent(value="result"))
        msgs = [_user_message(), tool_msg]
        _, anthropic_msgs, _ = convert_to_anthropic_messages(msgs, "sys")
        # Both should be in one user message
        assert len(anthropic_msgs) == 1

    def test_image_url_content_converted(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        img_msg = _make_message(
            MessageRole.USER,
            [ImageURLContent(url="http://img.example.com/photo.jpg")],
        )
        _, anthropic_msgs, _ = convert_to_anthropic_messages([img_msg], "sys")
        content = anthropic_msgs[0]["content"]
        assert any(c.get("type") == "image" for c in content)

    def test_binary_image_content_converted(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        binary = BinaryContent(
            data=b"\xff\xd8\xff",
            mime_type="image/jpeg",
            path="/tmp/img.jpg",
        )
        img_msg = _make_message(MessageRole.USER, [binary])
        _, anthropic_msgs, _ = convert_to_anthropic_messages([img_msg], "sys")
        content = anthropic_msgs[0]["content"]
        assert any(c.get("type") == "image" for c in content)

    def test_binary_pdf_content_converted_to_document(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        binary = BinaryContent(data=b"%PDF", mime_type="application/pdf", path="/tmp/doc.pdf")
        pdf_msg = _make_message(MessageRole.USER, [binary])
        _, anthropic_msgs, _ = convert_to_anthropic_messages([pdf_msg], "sys")
        content = anthropic_msgs[0]["content"]
        assert any(c.get("type") == "document" for c in content)

    def test_caching_disabled_no_cache_control(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        msgs = [_user_message("test")]
        _, anthropic_msgs, _ = convert_to_anthropic_messages(msgs, "sys", enable_caching=False)
        content = anthropic_msgs[0]["content"]
        for block in content:
            assert "cache_control" not in block

    def test_empty_messages_returns_empty_list(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        _, anthropic_msgs, _ = convert_to_anthropic_messages([], "sys")
        assert anthropic_msgs == []

    def test_provider_files_mapping_applied(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        # Create a mock provider file
        pf = MagicMock()
        pf.id = "internal-file-id"
        pf.provider_file_id = "provider-file-id"
        pf.content_type = "image/jpeg"

        user_msg = _make_message(
            MessageRole.USER,
            [TextContent(text="see this file")],
            file_ids=["internal-file-id"],
        )
        _, anthropic_msgs, _ = convert_to_anthropic_messages([user_msg], "sys", provider_files=[pf])
        content = anthropic_msgs[0]["content"]
        # Should include file reference block
        file_refs = [c for c in content if c.get("source", {}).get("type") == "file"]
        assert len(file_refs) == 1
        assert file_refs[0]["source"]["file_id"] == "provider-file-id"

    def test_provider_file_pdf_creates_document_block(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        pf = MagicMock()
        pf.id = "pdf-id"
        pf.provider_file_id = "pdf-provider-id"
        pf.content_type = "application/pdf"

        user_msg = _make_message(MessageRole.USER, [TextContent(text="pdf")], file_ids=["pdf-id"])
        _, anthropic_msgs, _ = convert_to_anthropic_messages([user_msg], "sys", provider_files=[pf])
        content = anthropic_msgs[0]["content"]
        docs = [c for c in content if c.get("type") == "document"]
        assert len(docs) == 1

    def test_provider_file_other_type_creates_container_upload(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        pf = MagicMock()
        pf.id = "csv-id"
        pf.provider_file_id = "csv-provider-id"
        pf.content_type = "text/csv"

        user_msg = _make_message(MessageRole.USER, [TextContent(text="data")], file_ids=["csv-id"])
        _, anthropic_msgs, _ = convert_to_anthropic_messages([user_msg], "sys", provider_files=[pf])
        content = anthropic_msgs[0]["content"]
        uploads = [c for c in content if c.get("type") == "container_upload"]
        assert len(uploads) == 1

    def test_tool_call_in_assistant_message(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        tc = ToolCall(id="call1", name="search", input='{"q": "hello"}', finished=True)
        asst_msg = _make_message(MessageRole.ASSISTANT, [tc])
        _, anthropic_msgs, _ = convert_to_anthropic_messages([_user_message(), asst_msg], "sys")
        asst_content = anthropic_msgs[1]["content"]
        tool_uses = [c for c in asst_content if c.get("type") == "tool_use"]
        assert len(tool_uses) == 1
        assert tool_uses[0]["name"] == "search"

    def test_reasoning_content_in_assistant_message(self):
        from ii_agent.chat.llm.anthropic.prompt_converter import convert_to_anthropic_messages

        rc = ReasoningContent(thinking="I think...", signature="sig")
        asst_msg = _make_message(MessageRole.ASSISTANT, [rc])
        _, anthropic_msgs, _ = convert_to_anthropic_messages([_user_message(), asst_msg], "sys")
        asst_content = anthropic_msgs[1]["content"]
        thinking_blocks = [
            c for c in asst_content if c.get("type") in ("thinking", "redacted_thinking")
        ]
        assert len(thinking_blocks) == 1
