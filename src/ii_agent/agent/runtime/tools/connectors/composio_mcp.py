"""Composio MCP Tool Loader - loads user's Composio tools from database.

This module:
1. Loads user's Composio profiles from database
2. Gets available actions from Composio SDK
3. Converts actions to ComposioMCPTool format for agent execution
"""

from typing import Any, Dict, List, Optional

from composio import Composio
from sqlalchemy import select

from ii_agent.core.db.manager import get_db_session_local
from ii_agent.integrations.connectors.models import ComposioProfile
from ii_agent.agent.runtime.tools.mcp.composio_mcp import ComposioMCPTool
from ii_agent.integrations.connectors.composio import ComposioCacheService, ToolkitService
from ii_agent.core.logger import logger


async def load_composio_tools_for_user(
    user_id: str,
    composio_api_key: str,
) -> List[ComposioMCPTool]:
    """Load all available Composio tools for a user from database.

    This function:
    1. Queries active Composio profiles from database
    2. Gets actions from Composio SDK for each profile
    3. Converts each action to ComposioMCPTool format

    Args:
        user_id: User ID to load tools for
        composio_api_key: Composio API key for SDK access

    Returns:
        List of ComposioMCPTool instances ready for agent execution
    """
    tools: List[ComposioMCPTool] = []

    try:
        # Load active Composio profiles from database
        async with get_db_session_local() as db:
            result = await db.execute(
                select(ComposioProfile).where(
                    ComposioProfile.user_id == user_id,
                    ComposioProfile.status == "enable",
                )
            )
            profiles = result.scalars().all()

        if not profiles:
            logger.info(f"No active Composio profiles found for user {user_id}")
            return tools

        logger.info(f"Found {len(profiles)} active Composio profiles for user {user_id}")

        # Initialize Composio client
        composio_client = Composio(api_key=composio_api_key)

        # Initialize ToolkitService for fetching logos
        toolkit_service = ToolkitService()

        # Load tools for each profile
        for profile in profiles:
            try:
                logger.info(
                    f"Loading tools for {profile.toolkit_name} (toolkit: {profile.toolkit_slug})"
                )

                # Get toolkit logo from cache/API
                toolkit_logo = await toolkit_service.get_toolkit_icon(profile.toolkit_slug)

                # Try to get actions from cache first
                cached_data = await ComposioCacheService.get_toolkit_actions(profile.toolkit_slug)

                if cached_data and cached_data.get("actions"):
                    logger.debug(f"Using cached actions for toolkit {profile.toolkit_slug}")
                    actions = cached_data["actions"]
                else:
                    from ii_agent.integrations.connectors.composio.default_toolkit_tools import (
                        get_default_tools,
                    )

                    # Get actions from Composio SDK
                    logger.debug(
                        f"Fetching actions from Composio SDK for toolkit {profile.toolkit_slug}"
                    )
                    actions = composio_client.tools.get(
                        user_id=profile.composio_user_id,
                        toolkits=[profile.toolkit_slug],
                        limit=1000,
                    )

                    # Extract metadata
                    formatted_actions = []
                    categories = set()
                    default_tool_slugs = set(get_default_tools(profile.toolkit_slug))

                    # Get excepted actions for this toolkit
                    excepted_actions = ToolkitService.EXCEPT_TOOLKIT.get(profile.toolkit_slug, [])

                    for action in actions:
                        name, description, parameters = _extract_action_metadata(action)

                        # Skip if action is in the exception list
                        if name in excepted_actions:
                            logger.debug(f"Skipping excepted action: {name}")
                            continue

                        # Formatted action data for API response
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
                        profile.toolkit_slug,
                        actions_data=formatted_actions,
                        categories=sorted(list(categories)),
                    )
                    actions = formatted_actions

                # Filter by enabled_tools if specified
                enabled_tools = profile.enabled_tools if profile.enabled_tools else []

                if not enabled_tools:
                    return tools
                # Create a lookup map of actions by name
                actions_map = {}
                for action in actions:
                    action_name = _extract_action_metadata(action)[0]
                    actions_map[action_name] = action

                # Iterate through enabled_tools and find matching actions
                for tool_name in enabled_tools:
                    if tool_name in actions_map:
                        action = actions_map[tool_name]
                        tool = await _convert_composio_action_to_mcp_tool(
                            action=action,
                            entity_id=profile.composio_user_id,
                            connected_account_id=profile.connected_account_id,
                            composio_api_key=composio_api_key,
                            composio_client=composio_client,
                            mcp_server_id=profile.mcp_server_id,
                            tool_logo=toolkit_logo,
                        )
                        tools.append(tool)
                    else:
                        logger.warning(
                            f"Enabled tool '{tool_name}' not found in available actions for {profile.toolkit_name}"
                        )

                logger.info(
                    f"Loaded {len([t for t in tools if hasattr(t, '_composio_action_slug') and profile.toolkit_slug in t._composio_action_slug])} "
                    f"tools from {profile.toolkit_name}"
                )

            except Exception as e:
                logger.opt(exception=True).error(
                    f"Failed to load tools for profile {profile.id} ({profile.toolkit_name}): {e}"
                )

    except Exception as e:
        logger.opt(exception=True).error(f"Failed to load Composio tools for user {user_id}: {e}")

    return tools


async def _get_action_display_name(action_name: str, composio_client: Composio) -> str:
    """Get the display name for a Composio action from cache or API.

    Args:
        action_name: Action identifier (e.g., "GMAIL_SEND_EMAIL")
        composio_client: Composio SDK client

    Returns:
        Human-readable display name for the action
    """
    # Try cache first
    cached_display_name = await ComposioCacheService.get_action_display_name(action_name)
    if cached_display_name:
        return cached_display_name

    # Fetch from Composio API
    try:
        raw_tool = composio_client.tools.get_raw_composio_tool_by_slug(action_name)
        display_name = raw_tool.name if raw_tool and hasattr(raw_tool, "name") else action_name

        # Cache the display name
        await ComposioCacheService.set_action_display_name(action_name, display_name)

        return display_name
    except Exception as e:
        logger.warning(f"Failed to get display name for action {action_name}: {e}")
        return action_name


async def _convert_composio_action_to_mcp_tool(
    action: Any,
    entity_id: str,
    connected_account_id: str,
    composio_api_key: str,
    composio_client: Composio,
    mcp_server_id: str = None,
    tool_logo: Optional[str] = None,
) -> ComposioMCPTool:
    """Convert a Composio action to ComposioMCPTool format.

    Args:
        action: Composio Action object from SDK
        entity_id: Composio entity/user ID (not used for MCP execution)
        connected_account_id: Connected account ID (not used for MCP execution)
        composio_api_key: Composio API key (not used for MCP execution)
        composio_client: Composio SDK client for fetching display names
        mcp_server_id: Composio MCP server ID
        tool_logo: URL for tool icon/logo

    Returns:
        ComposioMCPTool instance that will execute via MCP client to Composio MCP server
    """
    # Get action metadata
    name, description, parameters = _extract_action_metadata(action)

    # Get display name from cache or API
    display_name = await _get_action_display_name(name, composio_client)

    # Determine if read-only based on action name
    read_only = "read" in name.lower() or "get" in name.lower() or "list" in name.lower()

    # Create ComposioMCPTool instance
    # When executed, this tool will use self.mcp_client to call the Composio MCP server
    # The Composio MCP server is registered in the sandbox via _register_composio_mcp_servers()
    tool = ComposioMCPTool(
        name=name,
        display_name=display_name,
        description=description,
        input_schema=parameters,
        read_only=read_only,
        requires_confirmation=False,
        mcp_server_id=mcp_server_id,  # Composio MCP server ID
        tool_logo=tool_logo,
    )

    return tool


def _to_dict(obj: Any) -> Dict[str, Any]:
    """Convert various object types to dictionary."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump(exclude_none=True)
    if hasattr(obj, "dict"):
        return obj.dict(exclude_none=True)
    return {"type": "object", "properties": {}}


def _extract_action_metadata(action: Any) -> tuple[str, str, Dict[str, Any]]:
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

    return name, description, _to_dict(parameters)


async def resolve_tools(user_id: str, composio_api_key: str) -> List[ComposioMCPTool]:
    """Resolve all available Composio tools for a user.

    This is a convenience function that wraps load_composio_tools_for_user()
    for use in tool resolution systems.

    Args:
        user_id: User ID to resolve tools for
        composio_api_key: Composio API key

    Returns:
        List of ComposioMCPTool instances available for the user
    """
    return await load_composio_tools_for_user(
        user_id=user_id,
        composio_api_key=composio_api_key,
    )
