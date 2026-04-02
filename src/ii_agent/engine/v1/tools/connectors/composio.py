"""Composio tool integration using Composio SDK directly (not MCP)."""

import json
from typing import Any, Dict, List, Optional, Union

from composio import Composio
from composio.exceptions import ToolVersionRequiredError

from ii_agent.integrations.connectors.composio import ComposioCacheService, ToolkitService
from ii_agent.integrations.connectors.composio.default_toolkit_tools import get_default_tools
from ii_agent.core.logger import logger
from ii_agent.engine.v1.tools.base import (
    BaseAgentTool,
    TextContent,
    ToolConfirmationDetails,
    ToolResult,
)


def _to_dict(obj: Any) -> Dict[str, Any]:
    """Convert various object types to dictionary."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump(exclude_none=True)
    if hasattr(obj, "dict"):
        return obj.dict(exclude_none=True)
    return {"type": "object", "properties": {}}


class ComposioAgentTool(BaseAgentTool):
    """Tool for interacting with Composio-connected services.

    Uses the Composio SDK directly instead of MCP.
    """

    MAX_DISPLAY_ITEMS = 10

    def __init__(
        self,
        entity_id: str,
        toolkit_slug: str,
        toolkit_name: str,
        connected_account_id: str,
        composio_api_key: str,
        toolkit_logo: Optional[str] = None,
    ):
        """Initialize Composio tool."""
        self.entity_id = entity_id
        self.toolkit_slug = toolkit_slug
        self.toolkit_name = toolkit_name
        self.connected_account_id = connected_account_id
        self._client: Optional[Composio] = None  # type: ignore
        self._actions: Optional[List[Any]] = None
        self._composio_api_key = composio_api_key

        # Tool metadata
        self.name = f"composio_{toolkit_slug}"
        self.display_name = f"Composio {toolkit_name}"
        self.description = f"Access {toolkit_name} via Composio integration"
        self.read_only = False
        self.tool_logo: Optional[str] = toolkit_logo

    def _get_client(self) -> Composio:
        """Lazy-load the Composio SDK client."""
        if self._client is None:
            self._client = Composio(api_key=self._composio_api_key)
        return self._client

    async def _get_actions(self) -> List[Any]:
        """Get all actions for this toolkit with caching."""
        if self._actions is None:
            # Try to get actions from cache first
            cached_data = await ComposioCacheService.get_toolkit_actions(self.toolkit_slug)

            if cached_data and cached_data.get("actions"):
                logger.debug(f"Using cached actions for toolkit {self.toolkit_slug}")
                self._actions = cached_data["actions"]
            else:
                # Get actions from Composio SDK
                logger.debug(f"Fetching actions from Composio SDK for toolkit {self.toolkit_slug}")
                actions = self._get_client().tools.get(
                    user_id=self.entity_id,
                    toolkits=[self.toolkit_slug],
                    limit=1000,
                )

                # Extract metadata and format actions
                formatted_actions = []
                categories = set()
                default_tool_slugs = set(get_default_tools(self.toolkit_slug))

                # Get excepted actions for this toolkit
                excepted_actions = ToolkitService.EXCEPT_TOOLKIT.get(self.toolkit_slug, [])
                if actions:
                    for action in actions:
                        name, description, parameters = self._extract_action_metadata(action)

                        # Skip if action is in the exception list
                        if name in excepted_actions:
                            logger.debug(f"Skipping excepted action: {name}")
                            continue

                        # Extract category from action name
                        parts = name.split("_")
                        category = parts[1] if len(parts) > 1 else "OTHER"
                        categories.add(category)

                        formatted_actions.append(
                            {
                                "name": name,
                                "description": description,
                                "category": category,
                                "read_only": "read" in name.lower()
                                or "get" in name.lower()
                                or "list" in name.lower(),
                                "display_name": name,
                                "default_enabled": name in default_tool_slugs,
                                "parameters": parameters,
                            }
                        )

                    # Cache formatted actions
                    await ComposioCacheService.set_toolkit_actions(
                        self.toolkit_slug,
                        actions_data=formatted_actions,
                        categories=sorted(list(categories)),
                    )

                    self._actions = formatted_actions

                return self._actions

    async def get_sub_tools(self) -> List[BaseAgentTool]:
        """Get individual action tools for this Composio integration."""
        all_actions = await self._get_actions()

        # Filter by enabled_tools if specified (empty means all enabled)
        enabled_tools = getattr(self, "enabled_tools", []) or []
        enabled_set = {tool.lower() for tool in enabled_tools}

        action_tools: List[BaseAgentTool] = []
        for action in all_actions:
            # Actions are already formatted dictionaries from _get_actions
            name = action.get("name", "")
            description = action.get("description", "")
            parameters = action.get("parameters", {})

            if enabled_set and name.lower() not in enabled_set:
                continue

            action_tools.append(
                ComposioActionTool(
                    parent_tool=self,
                    action_name=name,
                    action_description=description,
                    action_parameters=parameters,
                )
            )

        return action_tools

    def should_confirm_execute(
        self, tool_input: Dict[str, Any]
    ) -> Union[ToolConfirmationDetails, bool]:
        """No confirmation needed for Composio tools."""
        return False

    async def execute(self, tool_input: Dict[str, Any]) -> ToolResult:
        """Execute a Composio action.

        Args:
            tool_input: Must include 'action' key with action name,
                       and 'params' with action parameters
        """
        action_name = tool_input.get("action")
        params = tool_input.get("params", {})

        if not action_name:
            return self._error_result("Action name is required")

        try:
            result = self._get_client().tools.execute(
                slug=action_name,
                arguments=params,
                connected_account_id=self.connected_account_id,
                user_id=self.entity_id,
                dangerously_skip_version_check=True,
            )
            return self._parse_result(action_name, result)

        except ToolVersionRequiredError:
            return self._error_result(
                "Composio requires a specific toolkit version. "
                "Set COMPOSIO_TOOLKIT_VERSION_<TOOLKIT> or provide a version."
            )

        except Exception as e:
            logger.error(f"Error executing Composio action {action_name}: {e}", exc_info=True)
            return self._error_result(f"Error executing {action_name}: {str(e)}")

    def _extract_action_metadata(self, action: Any) -> (str, str, Dict[str, Any]):  # type: ignore
        """Handle action metadata whether returned as dict or SDK object."""
        if isinstance(action, dict):
            fn_data = action.get("function", {}) if isinstance(action.get("function"), dict) else {}
            name = fn_data.get("name") or action.get("name", "")
            description = fn_data.get("description") or action.get("description", "")
            parameters = (
                fn_data.get("parameters")
                or action.get("input_parameters")
                or action.get("parameters", {})
            )
        else:
            fn = getattr(action, "function", None)
            name = getattr(fn, "name", "") or getattr(action, "name", "")
            description = getattr(fn, "description", "") or getattr(action, "description", "")
            parameters = (
                getattr(fn, "parameters", None)
                or getattr(action, "input_parameters", {})
                or getattr(action, "parameters", {})
            )

        name = name or ""

        return name, description, _to_dict(parameters)

    def _error_result(self, message: str) -> ToolResult:
        """Create an error ToolResult."""
        return ToolResult(
            llm_content=f"Error: {message}",
            user_display_content=f"Error: {message}",
            is_error=True,
        )

    def _parse_result(self, action_name: str, result: dict[Any, Any] | Any) -> ToolResult:
        """Parse Composio action result into ToolResult."""
        # Composio uses both 'successful' and 'successfull' spellings
        is_success = result.get("successful") or result.get("successfull")

        if not is_success:
            error_msg = result.get("error", "Unknown error")
            return self._error_result(f"Action failed: {error_msg}")

        error = result.get("error")
        if error:
            return self._error_result(f"Action completed with error: {error}")

        data = result.get("data", {})
        response_text = self._format_response(action_name, data)

        return ToolResult(
            llm_content=[TextContent(type="text", text=response_text)],
            user_display_content=response_text,
            is_error=False,
        )

    def _format_response(self, action_name: str, data: Dict) -> str:
        """Format Composio response data for display."""
        # Handle list responses (e.g., calendar events)
        items = data.get("items")
        if isinstance(items, list):
            return self._format_items_list(action_name, items)

        return json.dumps(data, indent=2)

    def _format_items_list(self, action_name: str, items: List) -> str:
        """Format a list of items for display."""
        if not items:
            return f"No items found for {action_name}"

        lines = [f"Found {len(items)} items:\n"]

        for i, item in enumerate(items[: self.MAX_DISPLAY_ITEMS], 1):
            if isinstance(item, dict) and "summary" in item:
                lines.append(f"{i}. {item['summary']}")
                start = item.get("start", {})
                start_time = start.get("dateTime") or start.get("date")
                if start_time:
                    lines.append(f"   Start: {start_time}")
            else:
                lines.append(f"{i}. {item}")

        if len(items) > self.MAX_DISPLAY_ITEMS:
            lines.append(f"\n... and {len(items) - self.MAX_DISPLAY_ITEMS} more items")

        return "\n".join(lines)


class ComposioActionTool(BaseAgentTool):
    """Individual Composio action tool."""

    # Keywords that indicate a mutating operation
    MUTATING_KEYWORDS = ("delete", "update", "create", "remove", "modify")

    def __init__(
        self,
        parent_tool: ComposioAgentTool,
        action_name: str,
        action_description: str,
        action_parameters: Any,
    ):
        self.parent_tool = parent_tool
        self.action_name = action_name or ""
        self.name = self.action_name.lower()
        self.display_name = self.action_name
        self.description = action_description
        self.input_schema = _to_dict(action_parameters)

        # Get logo from parent tool if available
        self.tool_logo = self.parent_tool.tool_logo

        # Determine if this is a read-only action
        action_lower = action_name.lower()
        self.read_only = not any(kw in action_lower for kw in self.MUTATING_KEYWORDS)

    def info(self):
        """Return tool info for chat service compatibility."""
        from ii_agent.chat.tools.base import ToolInfo

        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters=self.input_schema,
            required=self.input_schema.get("required", [])
            if isinstance(self.input_schema, dict)
            else [],
        )

    def should_confirm_execute(
        self, tool_input: Dict[str, Any]
    ) -> Union[ToolConfirmationDetails, bool]:
        return False

    def _parse_input(self, tool_input: Any) -> Dict[str, Any]:
        """Parse tool input which may be string or dict."""
        if isinstance(tool_input, str):
            return json.loads(tool_input)
        return tool_input

    def _format_llm_content(self, content: Any) -> str:
        """Format LLM content to string."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(item.text if hasattr(item, "text") else str(item) for item in content)
        return str(content)

    async def run(self, tool_call):
        """Execute tool for chat service compatibility."""
        from ii_agent.chat.schemas import ErrorTextContent, TextResultContent
        from ii_agent.chat.tools.base import ToolResponse

        try:
            params = self._parse_input(tool_call.input)
            result = await self.execute(params)

            if result.is_error:
                return ToolResponse(
                    output=ErrorTextContent(value=str(result.llm_content)), error=True
                )

            return ToolResponse(
                output=TextResultContent(value=self._format_llm_content(result.llm_content)),
                error=False,
            )

        except Exception as e:
            logger.error(f"Error executing Composio action {self.name}: {e}", exc_info=True)
            return ToolResponse(output=ErrorTextContent(value=f"Error: {str(e)}"), error=True)

    async def execute(self, tool_input: Dict[str, Any]) -> ToolResult:
        """Execute this specific action via the parent tool."""
        return await self.parent_tool.execute(
            {
                "action": self.action_name,
                "params": tool_input,
            }
        )
