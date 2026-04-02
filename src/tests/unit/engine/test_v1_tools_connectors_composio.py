"""Unit tests for Composio connector tool."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agents.tools.connectors.composio import (
    ComposioAgentTool,
    ComposioActionTool,
    _to_dict,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_composio_tool(**kwargs) -> ComposioAgentTool:
    defaults = {
        "entity_id": "entity-001",
        "toolkit_slug": "gmail",
        "toolkit_name": "Gmail",
        "connected_account_id": "account-001",
        "composio_api_key": "test-api-key",
    }
    defaults.update(kwargs)
    return ComposioAgentTool(**defaults)


def make_action_tool(
    parent=None, action_name="GMAIL_SEND_EMAIL", description="Send email", params=None
):
    if parent is None:
        parent = make_composio_tool()
    return ComposioActionTool(
        parent_tool=parent,
        action_name=action_name,
        action_description=description,
        action_parameters=params or {"type": "object", "properties": {}},
    )


# ---------------------------------------------------------------------------
# _to_dict utility tests
# ---------------------------------------------------------------------------


class TestToDict:
    def test_dict_input_returned_as_is(self):
        d = {"key": "value"}
        assert _to_dict(d) is d

    def test_object_with_model_dump(self):
        obj = MagicMock()
        obj.model_dump.return_value = {"dumped": True}
        result = _to_dict(obj)
        assert result == {"dumped": True}
        obj.model_dump.assert_called_once_with(exclude_none=True)

    def test_object_with_dict_method(self):
        obj = MagicMock(spec=["dict"])
        obj.dict.return_value = {"from_dict": True}
        result = _to_dict(obj)
        assert result == {"from_dict": True}

    def test_unknown_object_returns_fallback(self):
        result = _to_dict(42)
        assert result == {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# ComposioAgentTool __init__ tests
# ---------------------------------------------------------------------------


class TestComposioAgentToolInit:
    def test_init_sets_all_attributes(self):
        tool = make_composio_tool()
        assert tool.entity_id == "entity-001"
        assert tool.toolkit_slug == "gmail"
        assert tool.toolkit_name == "Gmail"
        assert tool.connected_account_id == "account-001"
        assert tool.name == "composio_gmail"
        assert tool.display_name == "Composio Gmail"
        assert "Gmail" in tool.description
        assert tool.read_only is False

    def test_init_with_logo(self):
        tool = make_composio_tool(toolkit_logo="http://example.com/logo.png")
        assert tool.tool_logo == "http://example.com/logo.png"

    def test_init_without_logo(self):
        tool = make_composio_tool()
        assert tool.tool_logo is None

    def test_client_initially_none(self):
        tool = make_composio_tool()
        assert tool._client is None

    def test_actions_initially_none(self):
        tool = make_composio_tool()
        assert tool._actions is None


# ---------------------------------------------------------------------------
# _get_client lazy loading tests
# ---------------------------------------------------------------------------


class TestGetClient:
    def test_get_client_creates_composio_instance(self):
        tool = make_composio_tool()
        with patch("ii_agent.agents.tools.connectors.composio.Composio") as MockComposio:
            mock_instance = MagicMock()
            MockComposio.return_value = mock_instance
            client = tool._get_client()
            MockComposio.assert_called_once_with(api_key="test-api-key")
            assert client is mock_instance

    def test_get_client_cached_on_second_call(self):
        tool = make_composio_tool()
        with patch("ii_agent.agents.tools.connectors.composio.Composio") as MockComposio:
            mock_instance = MagicMock()
            MockComposio.return_value = mock_instance
            client1 = tool._get_client()
            client2 = tool._get_client()
            assert MockComposio.call_count == 1
            assert client1 is client2


# ---------------------------------------------------------------------------
# _get_actions tests
# ---------------------------------------------------------------------------


class TestGetActions:
    @pytest.mark.asyncio
    async def test_get_actions_from_cache_sets_internal_state(self):
        """When _actions is pre-set, _get_actions does not fetch from cache."""
        tool = make_composio_tool()
        tool._actions = [{"name": "GMAIL_LIST", "description": "List", "parameters": {}}]

        with patch("ii_agent.agents.tools.connectors.composio.ComposioCacheService") as MockCache:
            MockCache.get_toolkit_actions = AsyncMock()
            await tool._get_actions()
            MockCache.get_toolkit_actions.assert_not_called()

        # _actions remains unchanged
        assert len(tool._actions) == 1

    @pytest.mark.asyncio
    async def test_get_actions_uses_cache_service(self):
        tool = make_composio_tool()
        cached = {"actions": [{"name": "GMAIL_LIST", "description": "List", "parameters": {}}]}

        with patch("ii_agent.agents.tools.connectors.composio.ComposioCacheService") as MockCache:
            MockCache.get_toolkit_actions = AsyncMock(return_value=cached)
            await tool._get_actions()

        assert tool._actions == cached["actions"]

    @pytest.mark.asyncio
    async def test_get_actions_fetches_from_sdk_when_no_cache(self):
        tool = make_composio_tool()
        mock_action = MagicMock()
        mock_fn = MagicMock()
        mock_fn.name = "GMAIL_SEND_EMAIL"
        mock_fn.description = "Send email"
        mock_fn.parameters = None
        mock_action.function = mock_fn
        mock_action.name = "GMAIL_SEND_EMAIL"
        mock_action.description = "Send email"

        with (
            patch("ii_agent.agents.tools.connectors.composio.ComposioCacheService") as MockCache,
            patch(
                "ii_agent.agents.tools.connectors.composio.get_default_tools",
                return_value=[],
            ),
            patch("ii_agent.agents.tools.connectors.composio.ToolkitService") as MockService,
        ):
            MockCache.get_toolkit_actions = AsyncMock(return_value=None)
            MockCache.set_toolkit_actions = AsyncMock()
            MockService.EXCEPT_TOOLKIT = {"gmail": []}

            mock_client = MagicMock()
            mock_client.tools.get.return_value = [mock_action]
            tool._client = mock_client

            result = await tool._get_actions()

        assert any(a["name"] == "GMAIL_SEND_EMAIL" for a in result)


# ---------------------------------------------------------------------------
# _extract_action_metadata tests
# ---------------------------------------------------------------------------


class TestExtractActionMetadata:
    def test_extract_from_dict_with_function_key(self):
        tool = make_composio_tool()
        action = {
            "function": {
                "name": "MY_ACTION",
                "description": "Does something",
                "parameters": {"type": "object"},
            }
        }
        name, desc, params = tool._extract_action_metadata(action)
        assert name == "MY_ACTION"
        assert desc == "Does something"

    def test_extract_from_dict_with_direct_name(self):
        tool = make_composio_tool()
        action = {"name": "DIRECT_ACTION", "description": "Direct desc"}
        name, desc, params = tool._extract_action_metadata(action)
        assert name == "DIRECT_ACTION"
        assert desc == "Direct desc"

    def test_extract_from_sdk_object(self):
        tool = make_composio_tool()
        action = MagicMock()
        fn = MagicMock()
        fn.name = "SDK_ACTION"
        fn.description = "SDK desc"
        fn.parameters = None
        action.function = fn
        action.input_parameters = None
        action.parameters = None
        name, desc, _ = tool._extract_action_metadata(action)
        assert name == "SDK_ACTION"
        assert desc == "SDK desc"

    def test_extract_name_defaults_to_empty_string(self):
        tool = make_composio_tool()
        action = {}
        name, _, _ = tool._extract_action_metadata(action)
        assert name == ""


# ---------------------------------------------------------------------------
# _error_result tests
# ---------------------------------------------------------------------------


class TestErrorResult:
    def test_error_result_structure(self):
        tool = make_composio_tool()
        result = tool._error_result("Something went wrong")
        assert result.is_error is True
        assert "Something went wrong" in result.llm_content
        assert "Something went wrong" in result.user_display_content

    def test_error_result_prefixes_with_error(self):
        tool = make_composio_tool()
        result = tool._error_result("Test message")
        assert result.llm_content.startswith("Error:")


# ---------------------------------------------------------------------------
# _parse_result tests
# ---------------------------------------------------------------------------


class TestParseResult:
    def test_parse_successful_result(self):
        tool = make_composio_tool()
        result_data = {"successful": True, "data": {"items": []}}
        result = tool._parse_result("MY_ACTION", result_data)
        assert result.is_error is False

    def test_parse_failed_result(self):
        tool = make_composio_tool()
        result_data = {"successful": False, "error": "Action failed"}
        result = tool._parse_result("MY_ACTION", result_data)
        assert result.is_error is True
        assert "Action failed" in result.llm_content

    def test_parse_result_with_error_field_despite_success(self):
        tool = make_composio_tool()
        result_data = {"successful": True, "error": "partial error", "data": {}}
        result = tool._parse_result("MY_ACTION", result_data)
        assert result.is_error is True

    def test_parse_result_uses_successfull_spelling(self):
        tool = make_composio_tool()
        result_data = {"successfull": True, "data": {}}
        result = tool._parse_result("MY_ACTION", result_data)
        assert result.is_error is False


# ---------------------------------------------------------------------------
# _format_response tests
# ---------------------------------------------------------------------------


class TestFormatResponse:
    def test_format_response_with_items_list(self):
        tool = make_composio_tool()
        data = {"items": [{"summary": "Item 1"}, {"summary": "Item 2"}]}
        result = tool._format_response("LIST_EVENTS", data)
        assert "Found 2 items" in result
        assert "Item 1" in result

    def test_format_response_non_list_returns_json(self):
        tool = make_composio_tool()
        data = {"key": "value", "count": 42}
        result = tool._format_response("GET_ITEM", data)
        parsed = json.loads(result)
        assert parsed["key"] == "value"


# ---------------------------------------------------------------------------
# _format_items_list tests
# ---------------------------------------------------------------------------


class TestFormatItemsList:
    def test_empty_items_returns_no_items_found(self):
        tool = make_composio_tool()
        result = tool._format_items_list("MY_ACTION", [])
        assert "No items found" in result

    def test_items_with_summary_key_formatted(self):
        tool = make_composio_tool()
        items = [{"summary": "Meeting 1", "start": {"dateTime": "2024-01-01T10:00:00"}}]
        result = tool._format_items_list("LIST_EVENTS", items)
        assert "Meeting 1" in result
        assert "2024-01-01T10:00:00" in result

    def test_items_without_summary_formatted_as_string(self):
        tool = make_composio_tool()
        items = [{"title": "No summary key"}]
        result = tool._format_items_list("LIST", items)
        assert "No summary key" in result

    def test_more_than_max_items_shows_truncation_message(self):
        tool = make_composio_tool()
        items = [{"summary": f"Item {i}"} for i in range(15)]
        result = tool._format_items_list("LIST", items)
        assert "more items" in result

    def test_exactly_max_items_no_truncation(self):
        tool = make_composio_tool()
        items = [{"summary": f"Item {i}"} for i in range(10)]
        result = tool._format_items_list("LIST", items)
        assert "more items" not in result


# ---------------------------------------------------------------------------
# should_confirm_execute tests
# ---------------------------------------------------------------------------


class TestShouldConfirmExecute:
    def test_always_returns_false(self):
        tool = make_composio_tool()
        assert tool.should_confirm_execute({}) is False


# ---------------------------------------------------------------------------
# get_sub_tools tests
# ---------------------------------------------------------------------------


class TestGetSubTools:
    @pytest.mark.asyncio
    async def test_get_sub_tools_returns_action_tools(self):
        """get_sub_tools should call _get_actions and return ComposioActionTool instances."""
        tool = make_composio_tool()
        actions = [
            {
                "name": "GMAIL_SEND_EMAIL",
                "description": "Send an email",
                "parameters": {"type": "object", "properties": {}},
            }
        ]
        # Patch _get_actions to return the actions
        with patch.object(tool, "_get_actions", new_callable=AsyncMock, return_value=actions):
            sub_tools = await tool.get_sub_tools()
        assert len(sub_tools) == 1
        assert isinstance(sub_tools[0], ComposioActionTool)
        assert sub_tools[0].action_name == "GMAIL_SEND_EMAIL"

    @pytest.mark.asyncio
    async def test_get_sub_tools_filters_by_enabled_tools(self):
        tool = make_composio_tool()
        tool.enabled_tools = ["gmail_send_email"]
        actions = [
            {"name": "GMAIL_SEND_EMAIL", "description": "Send", "parameters": {}},
            {"name": "GMAIL_READ_EMAIL", "description": "Read", "parameters": {}},
        ]
        with patch.object(tool, "_get_actions", new_callable=AsyncMock, return_value=actions):
            sub_tools = await tool.get_sub_tools()
        assert len(sub_tools) == 1
        assert sub_tools[0].action_name == "GMAIL_SEND_EMAIL"

    @pytest.mark.asyncio
    async def test_get_sub_tools_with_empty_actions_returns_empty(self):
        tool = make_composio_tool()
        with patch.object(tool, "_get_actions", new_callable=AsyncMock, return_value=[]):
            sub_tools = await tool.get_sub_tools()
        assert sub_tools == []


# ---------------------------------------------------------------------------
# execute tests
# ---------------------------------------------------------------------------


class TestComposioAgentToolExecute:
    @pytest.mark.asyncio
    async def test_execute_requires_action_name(self):
        tool = make_composio_tool()
        result = await tool.execute({})
        assert result.is_error is True
        assert "Action name is required" in result.llm_content

    @pytest.mark.asyncio
    async def test_execute_successful_action(self):
        tool = make_composio_tool()
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = {"successful": True, "data": {"status": "sent"}}
        tool._client = mock_client

        result = await tool.execute(
            {"action": "GMAIL_SEND_EMAIL", "params": {"to": "test@example.com"}}
        )
        assert result.is_error is False

    @pytest.mark.asyncio
    async def test_execute_handles_tool_version_error(self):
        """Test that ToolVersionRequiredError is caught and converted to an error result."""
        from composio.exceptions import ToolVersionRequiredError

        tool = make_composio_tool()
        mock_client = MagicMock()
        # ToolVersionRequiredError takes no arguments (no-arg constructor)
        mock_client.tools.execute.side_effect = ToolVersionRequiredError()
        tool._client = mock_client

        result = await tool.execute({"action": "GMAIL_SEND_EMAIL", "params": {}})
        assert result.is_error is True

    @pytest.mark.asyncio
    async def test_execute_handles_generic_exception(self):
        tool = make_composio_tool()
        mock_client = MagicMock()
        mock_client.tools.execute.side_effect = RuntimeError("unexpected error")
        tool._client = mock_client

        result = await tool.execute({"action": "GMAIL_SEND_EMAIL", "params": {}})
        assert result.is_error is True
        assert "unexpected error" in result.llm_content


# ---------------------------------------------------------------------------
# ComposioActionTool tests
# ---------------------------------------------------------------------------


class TestComposioActionToolInit:
    def test_init_sets_attributes(self):
        action_tool = make_action_tool()
        assert action_tool.action_name == "GMAIL_SEND_EMAIL"
        assert action_tool.name == "gmail_send_email"
        assert action_tool.display_name == "GMAIL_SEND_EMAIL"
        assert action_tool.description == "Send email"

    def test_read_only_for_non_mutating_action(self):
        action_tool = make_action_tool(action_name="GMAIL_LIST_EMAILS")
        assert action_tool.read_only is True

    def test_not_read_only_for_mutating_action(self):
        action_tool = make_action_tool(action_name="GMAIL_CREATE_DRAFT")
        assert action_tool.read_only is False

    def test_inherits_logo_from_parent(self):
        parent = make_composio_tool(toolkit_logo="http://example.com/logo.png")
        action_tool = make_action_tool(parent=parent)
        assert action_tool.tool_logo == "http://example.com/logo.png"

    def test_empty_action_name_defaults(self):
        parent = make_composio_tool()
        action_tool = ComposioActionTool(
            parent_tool=parent,
            action_name="",
            action_description="desc",
            action_parameters={},
        )
        assert action_tool.action_name == ""
        assert action_tool.name == ""


class TestComposioActionToolReadOnly:
    def test_delete_action_not_read_only(self):
        action_tool = make_action_tool(action_name="GMAIL_DELETE_EMAIL")
        assert action_tool.read_only is False

    def test_update_action_not_read_only(self):
        action_tool = make_action_tool(action_name="GMAIL_UPDATE_DRAFT")
        assert action_tool.read_only is False

    def test_get_action_is_read_only(self):
        action_tool = make_action_tool(action_name="GMAIL_GET_EMAIL")
        assert action_tool.read_only is True


class TestComposioActionToolShouldConfirm:
    def test_should_confirm_returns_false(self):
        action_tool = make_action_tool()
        assert action_tool.should_confirm_execute({}) is False


class TestComposioActionToolParseInput:
    def test_parse_dict_input(self):
        action_tool = make_action_tool()
        result = action_tool._parse_input({"key": "value"})
        assert result == {"key": "value"}

    def test_parse_string_input(self):
        action_tool = make_action_tool()
        result = action_tool._parse_input('{"key": "value"}')
        assert result == {"key": "value"}


class TestComposioActionToolFormatLlmContent:
    def test_string_content_returned_as_is(self):
        action_tool = make_action_tool()
        assert action_tool._format_llm_content("hello") == "hello"

    def test_list_content_joined(self):
        action_tool = make_action_tool()
        item1 = MagicMock()
        item1.text = "Part 1"
        item2 = MagicMock()
        item2.text = "Part 2"
        result = action_tool._format_llm_content([item1, item2])
        assert "Part 1" in result
        assert "Part 2" in result

    def test_other_types_converted_to_str(self):
        action_tool = make_action_tool()
        result = action_tool._format_llm_content(42)
        assert result == "42"


class TestComposioActionToolExecute:
    @pytest.mark.asyncio
    async def test_execute_delegates_to_parent(self):
        parent = make_composio_tool()
        parent.execute = AsyncMock(return_value=MagicMock(is_error=False, llm_content="ok"))
        action_tool = make_action_tool(parent=parent)

        result = await action_tool.execute({"to": "test@example.com"})

        parent.execute.assert_awaited_once_with(
            {
                "action": "GMAIL_SEND_EMAIL",
                "params": {"to": "test@example.com"},
            }
        )
        assert result.llm_content == "ok"
