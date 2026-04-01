"""Unit tests for ii_agent/agent/runtime/tools/base.py.

Tests cover:
- UserInputField dataclass: to_dict(), from_dict()
- ToolParam model validation
- ToolResult model validation
- ToolConfirmationDetails model
- FileURLContent model
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# UserInputField
# ---------------------------------------------------------------------------


class TestUserInputField:
    """Tests for the UserInputField dataclass."""

    def test_create_with_required_fields(self):
        from ii_agent.agents.tools.base import UserInputField

        field = UserInputField(name="username", field_type=str)
        assert field.name == "username"
        assert field.field_type is str

    def test_description_defaults_to_none(self):
        from ii_agent.agents.tools.base import UserInputField

        field = UserInputField(name="field", field_type=int)
        assert field.description is None

    def test_value_defaults_to_none(self):
        from ii_agent.agents.tools.base import UserInputField

        field = UserInputField(name="field", field_type=str)
        assert field.value is None

    def test_create_with_all_fields(self):
        from ii_agent.agents.tools.base import UserInputField

        field = UserInputField(
            name="age",
            field_type=int,
            description="User's age",
            value=25,
        )
        assert field.name == "age"
        assert field.field_type is int
        assert field.description == "User's age"
        assert field.value == 25

    def test_to_dict_returns_name(self):
        from ii_agent.agents.tools.base import UserInputField

        field = UserInputField(name="my_field", field_type=str)
        result = field.to_dict()
        assert result["name"] == "my_field"

    def test_to_dict_returns_field_type_as_string(self):
        from ii_agent.agents.tools.base import UserInputField

        field = UserInputField(name="count", field_type=int)
        result = field.to_dict()
        assert result["field_type"] == "int"

    def test_to_dict_returns_description(self):
        from ii_agent.agents.tools.base import UserInputField

        field = UserInputField(name="f", field_type=str, description="A string field")
        result = field.to_dict()
        assert result["description"] == "A string field"

    def test_to_dict_returns_value(self):
        from ii_agent.agents.tools.base import UserInputField

        field = UserInputField(name="f", field_type=str, value="hello")
        result = field.to_dict()
        assert result["value"] == "hello"

    def test_to_dict_description_none_when_not_set(self):
        from ii_agent.agents.tools.base import UserInputField

        field = UserInputField(name="f", field_type=str)
        result = field.to_dict()
        assert result["description"] is None

    def test_to_dict_value_none_when_not_set(self):
        from ii_agent.agents.tools.base import UserInputField

        field = UserInputField(name="f", field_type=bool)
        result = field.to_dict()
        assert result["value"] is None

    def test_from_dict_creates_correct_instance(self):
        from ii_agent.agents.tools.base import UserInputField

        data = {
            "name": "score",
            "field_type": "int",
            "description": "A score",
            "value": 42,
        }
        field = UserInputField.from_dict(data)
        assert field.name == "score"
        assert field.field_type is int
        assert field.description == "A score"
        assert field.value == 42

    def test_from_dict_with_str_type(self):
        from ii_agent.agents.tools.base import UserInputField

        data = {"name": "text", "field_type": "str", "description": None, "value": None}
        field = UserInputField.from_dict(data)
        assert field.field_type is str

    def test_from_dict_with_bool_type(self):
        from ii_agent.agents.tools.base import UserInputField

        data = {"name": "flag", "field_type": "bool", "description": None, "value": True}
        field = UserInputField.from_dict(data)
        assert field.field_type is bool
        assert field.value is True

    def test_roundtrip_to_dict_and_from_dict(self):
        from ii_agent.agents.tools.base import UserInputField

        original = UserInputField(
            name="email", field_type=str, description="Email address", value="a@b.com"
        )
        recovered = UserInputField.from_dict(original.to_dict())
        assert recovered.name == original.name
        assert recovered.field_type == original.field_type
        assert recovered.description == original.description
        assert recovered.value == original.value

    def test_to_dict_with_float_type(self):
        from ii_agent.agents.tools.base import UserInputField

        field = UserInputField(name="price", field_type=float, value=9.99)
        result = field.to_dict()
        assert result["field_type"] == "float"
        assert result["value"] == 9.99


# ---------------------------------------------------------------------------
# ToolParam
# ---------------------------------------------------------------------------


class TestToolParam:
    """Tests for the ToolParam Pydantic model."""

    def test_create_minimal_function_param(self):
        from ii_agent.agents.tools.base import ToolParam

        param = ToolParam(
            name="search",
            description="Searches the web",
            input_schema={"type": "object", "properties": {}},
        )
        assert param.name == "search"
        assert param.type == "function"

    def test_type_defaults_to_function(self):
        from ii_agent.agents.tools.base import ToolParam

        param = ToolParam(
            name="my_tool",
            description="Tool",
            input_schema={},
        )
        assert param.type == "function"

    def test_type_can_be_custom(self):
        from ii_agent.agents.tools.base import ToolParam

        param = ToolParam(
            type="custom",
            name="custom_tool",
            description="Custom",
            input_schema={},
        )
        assert param.type == "custom"

    def test_name_is_required(self):
        from ii_agent.agents.tools.base import ToolParam
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ToolParam(description="Missing name", input_schema={})

    def test_description_is_required(self):
        from ii_agent.agents.tools.base import ToolParam
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ToolParam(name="tool", input_schema={})

    def test_input_schema_is_required(self):
        from ii_agent.agents.tools.base import ToolParam
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ToolParam(name="tool", description="desc")

    def test_input_schema_accepts_complex_schema(self):
        from ii_agent.agents.tools.base import ToolParam

        schema = {
            "type": "object",
            "properties": {"q": {"type": "string", "description": "Query"}},
            "required": ["q"],
        }
        param = ToolParam(name="search", description="Search tool", input_schema=schema)
        assert param.input_schema["properties"]["q"]["type"] == "string"

    def test_invalid_type_raises_validation_error(self):
        from ii_agent.agents.tools.base import ToolParam
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ToolParam(type="invalid_type", name="t", description="d", input_schema={})


# ---------------------------------------------------------------------------
# ToolResult
# ---------------------------------------------------------------------------


class TestToolResult:
    """Tests for the ToolResult Pydantic model."""

    def test_create_with_string_llm_content(self):
        from ii_agent.agents.tools.base import ToolResult

        result = ToolResult(llm_content="Tool output text")
        assert result.llm_content == "Tool output text"

    def test_is_error_defaults_to_none(self):
        from ii_agent.agents.tools.base import ToolResult

        result = ToolResult(llm_content="ok")
        assert result.is_error is None

    def test_is_interrupted_defaults_to_false(self):
        from ii_agent.agents.tools.base import ToolResult

        result = ToolResult(llm_content="ok")
        assert result.is_interrupted is False

    def test_cost_defaults_to_zero(self):
        from ii_agent.agents.tools.base import ToolResult

        result = ToolResult(llm_content="ok")
        assert result.cost == 0.0

    def test_requires_user_input_defaults_to_false(self):
        from ii_agent.agents.tools.base import ToolResult

        result = ToolResult(llm_content="ok")
        assert result.requires_user_input is False

    def test_user_input_schema_defaults_to_none(self):
        from ii_agent.agents.tools.base import ToolResult

        result = ToolResult(llm_content="ok")
        assert result.user_input_schema is None

    def test_user_display_content_defaults_to_none(self):
        from ii_agent.agents.tools.base import ToolResult

        result = ToolResult(llm_content="ok")
        assert result.user_display_content is None

    def test_create_with_is_error_true(self):
        from ii_agent.agents.tools.base import ToolResult

        result = ToolResult(llm_content="error occurred", is_error=True)
        assert result.is_error is True

    def test_create_with_custom_cost(self):
        from ii_agent.agents.tools.base import ToolResult

        result = ToolResult(llm_content="image generated", cost=0.02)
        assert result.cost == 0.02

    def test_create_with_dict_user_display_content(self):
        from ii_agent.agents.tools.base import ToolResult

        result = ToolResult(llm_content="ok", user_display_content={"status": "done"})
        assert result.user_display_content == {"status": "done"}

    def test_create_with_list_user_display_content(self):
        from ii_agent.agents.tools.base import ToolResult

        result = ToolResult(llm_content="ok", user_display_content=[{"key": "val"}])
        assert isinstance(result.user_display_content, list)

    def test_create_with_list_llm_content(self):
        from ii_agent.agents.tools.base import ToolResult, TextContent

        text_block = TextContent(type="text", text="hello")
        result = ToolResult(llm_content=[text_block])
        assert isinstance(result.llm_content, list)
        assert result.llm_content[0].text == "hello"

    def test_requires_user_input_can_be_set_true(self):
        from ii_agent.agents.tools.base import ToolResult, UserInputField

        fields = [UserInputField(name="email", field_type=str)]
        result = ToolResult(
            llm_content="needs input",
            requires_user_input=True,
            user_input_schema=fields,
        )
        assert result.requires_user_input is True
        assert len(result.user_input_schema) == 1

    def test_is_interrupted_can_be_set_true(self):
        from ii_agent.agents.tools.base import ToolResult

        result = ToolResult(llm_content="interrupted", is_interrupted=True)
        assert result.is_interrupted is True


# ---------------------------------------------------------------------------
# ToolConfirmationDetails
# ---------------------------------------------------------------------------


class TestToolConfirmationDetails:
    """Tests for the ToolConfirmationDetails Pydantic model."""

    def test_create_with_edit_type(self):
        from ii_agent.agents.tools.base import ToolConfirmationDetails

        details = ToolConfirmationDetails(type="edit", message="About to edit file")
        assert details.type == "edit"
        assert details.message == "About to edit file"

    def test_create_with_bash_type(self):
        from ii_agent.agents.tools.base import ToolConfirmationDetails

        details = ToolConfirmationDetails(type="bash", message="About to run shell command")
        assert details.type == "bash"

    def test_create_with_mcp_type(self):
        from ii_agent.agents.tools.base import ToolConfirmationDetails

        details = ToolConfirmationDetails(type="mcp", message="MCP action")
        assert details.type == "mcp"

    def test_invalid_type_raises_validation_error(self):
        from ii_agent.agents.tools.base import ToolConfirmationDetails
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ToolConfirmationDetails(type="invalid", message="msg")

    def test_message_is_required(self):
        from ii_agent.agents.tools.base import ToolConfirmationDetails
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ToolConfirmationDetails(type="edit")

    def test_type_is_required(self):
        from ii_agent.agents.tools.base import ToolConfirmationDetails
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ToolConfirmationDetails(message="some message")


# ---------------------------------------------------------------------------
# FileURLContent
# ---------------------------------------------------------------------------


class TestFileURLContent:
    """Tests for the FileURLContent Pydantic model."""

    def test_create_valid_file_url_content(self):
        from ii_agent.agents.tools.base import FileURLContent

        content = FileURLContent(
            type="file_url",
            url="https://example.com/file.pdf",
            mime_type="application/pdf",
            name="document.pdf",
            size=1024,
        )
        assert content.type == "file_url"
        assert content.url == "https://example.com/file.pdf"
        assert content.mime_type == "application/pdf"
        assert content.name == "document.pdf"
        assert content.size == 1024

    def test_type_must_be_file_url(self):
        from ii_agent.agents.tools.base import FileURLContent
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            FileURLContent(
                type="wrong_type",
                url="https://example.com/f",
                mime_type="text/plain",
                name="f.txt",
                size=10,
            )

    def test_url_is_required(self):
        from ii_agent.agents.tools.base import FileURLContent
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            FileURLContent(type="file_url", mime_type="text/plain", name="f.txt", size=10)

    def test_mime_type_is_required(self):
        from ii_agent.agents.tools.base import FileURLContent
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            FileURLContent(type="file_url", url="https://example.com", name="f.txt", size=10)

    def test_name_is_required(self):
        from ii_agent.agents.tools.base import FileURLContent
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            FileURLContent(
                type="file_url",
                url="https://example.com",
                mime_type="text/plain",
                size=10,
            )

    def test_size_is_required(self):
        from ii_agent.agents.tools.base import FileURLContent
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            FileURLContent(
                type="file_url",
                url="https://example.com",
                mime_type="text/plain",
                name="f.txt",
            )

    def test_size_can_be_zero(self):
        from ii_agent.agents.tools.base import FileURLContent

        content = FileURLContent(
            type="file_url",
            url="https://example.com/empty",
            mime_type="text/plain",
            name="empty.txt",
            size=0,
        )
        assert content.size == 0

    def test_create_image_file_url_content(self):
        from ii_agent.agents.tools.base import FileURLContent

        content = FileURLContent(
            type="file_url",
            url="https://example.com/img.png",
            mime_type="image/png",
            name="photo.png",
            size=204800,
        )
        assert content.mime_type == "image/png"
        assert content.size == 204800
