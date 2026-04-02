"""Custom MCP Tool Loader - loads user's custom MCP tools from database.

This module:
1. Loads user's MCP settings from database
2. Connects to each MCP server to list available tools
3. Converts tools to UserMCPTool format for agent execution

Similar pattern to composio_mcp.py but for user-configured custom MCP servers.
"""

from typing import Any, List

from ii_agent.core.db import get_db_session_local
from ii_agent.core.redis import create_entity_cache
from ii_agent.core.container import get_app_container
from ii_agent.settings.mcp.schemas import MCPSettingList
from ii_agent.agents.factory.mcp.user_mcp_tool import UserMCPTool
from ii_agent.agents.factory.mcp.mcp_tool_loader import load_tools_from_mcp
from ii_agent.core.logger import logger

# Cache MCP tool definitions to avoid reconnecting to MCP servers on every request
_mcp_tools_cache = create_entity_cache(namespace="mcp_tools", ttl=14400)  # 4 hours


async def load_custom_mcp_tools_for_user(
    user_id: str,
) -> List[UserMCPTool]:
    """Load all available custom MCP tools for a user from database.

    This function:
    1. Queries active non-Composio MCP settings from database
    2. Connects to each MCP server to list tools
    3. Converts each tool to UserMCPTool format

    Args:
        user_id: User ID to load tools for

    Returns:
        List of UserMCPTool instances ready for agent execution
    """
    tools: List[UserMCPTool] = []

    try:
        # Load active MCP settings from database
        container = get_app_container()
        mcp_svc = container.mcp_setting_service
        async with get_db_session_local() as db:
            mcp_settings = await mcp_svc.list_mcp_settings(
                db,
                user_id=user_id,
                only_active=True,
            )

        if not mcp_settings or not mcp_settings.settings:
            logger.debug(f"No active MCP settings found for user {user_id}")
            return tools

        # Filter out Composio MCP settings (handled separately)
        non_composio_settings = [
            setting
            for setting in mcp_settings.settings
            if setting.metadata is None
            or getattr(setting.metadata, "tool_type", None)
            not in ("composio", "codex", "claude_code")
        ]

        if not non_composio_settings:
            logger.debug(f"No non-Composio MCP settings found for user {user_id}")
            return tools

        logger.info(
            f"Found {len(non_composio_settings)} active custom MCP settings for user {user_id}"
        )

        # Get combined configuration
        filtered_mcp_settings = MCPSettingList(settings=non_composio_settings)
        combined_config = filtered_mcp_settings.get_combined_active_config()

        if not combined_config.mcpServers:
            logger.debug(f"No MCP servers configured for user {user_id}")
            return tools

        # Load tools from each MCP server
        for server_name, server_config in combined_config.mcpServers.items():
            try:
                logger.info(f"Loading MCP tools from server: {server_name}")
                server_tools = await _load_tools_from_server(
                    server_name=server_name,
                    server_config=server_config,
                    user_id=user_id,
                )
                tools.extend(server_tools)
                logger.info(f"Loaded {len(server_tools)} tools from MCP server '{server_name}'")
            except Exception as e:
                logger.error(
                    f"Failed to load tools from MCP server '{server_name}': {e}",
                    exc_info=True,
                )

        logger.info(f"Loaded {len(tools)} total custom MCP tools for user {user_id}")

    except Exception as e:
        logger.error(
            f"Failed to load custom MCP tools for user {user_id}: {e}",
            exc_info=True,
        )

    return tools


async def _load_tools_from_server(
    server_name: str,
    server_config: Any,
    user_id: str,
) -> List[UserMCPTool]:
    """Load tools from a single MCP server, with Redis caching.

    Args:
        server_name: Name identifier for the server
        server_config: Server configuration (StdioMCPServer or RemoteMCPServer)
        user_id: User ID for cache key scoping

    Returns:
        List of UserMCPTool instances from this server
    """
    cache_key = f"{user_id}:{server_name}"

    # Try cache first to avoid reconnecting to the MCP server
    cached = await _mcp_tools_cache.get(cache_key)
    if cached and cached.get("tools"):
        logger.info(f"Cache hit for MCP tools: {cache_key}")
        return [
            UserMCPTool(
                name=t["name"],
                display_name=t["display_name"],
                description=t["description"],
                input_schema=t["input_schema"],
                read_only=t.get("read_only", False),
                requires_confirmation=False,
                mcp_server_id=server_name,
            )
            for t in cached["tools"]
        ]

    # Cache miss — connect to MCP server
    # Determine transport type
    if hasattr(server_config, "url"):
        # SSE/HTTP transport
        transport = server_config.url
        logger.debug(f"Using SSE transport for '{server_name}': {transport}")
    else:
        # Stdio transport - wrap in mcpServers config format expected by fastmcp
        server_dict = server_config.model_dump(exclude_none=True)
        transport = {"mcpServers": {server_name: server_dict}}
        logger.debug(
            f"Using stdio transport for '{server_name}': {server_dict.get('command', 'unknown')}"
        )

    # Load tools using v1 MCP loader (returns UserMCPTool instances directly)
    tools = await load_tools_from_mcp(
        transport=transport,
        timeout=60,
        mcp_server_id=server_name,
    )

    # Cache the tool definitions for next time
    if tools:
        tool_dicts = [
            {
                "name": t.name,
                "display_name": t.display_name,
                "description": t.description,
                "input_schema": t.input_schema,
                "read_only": t.read_only,
            }
            for t in tools
        ]
        await _mcp_tools_cache.set(cache_key, {"tools": tool_dicts})
        logger.info(f"Cached {len(tools)} MCP tools for key: {cache_key}")

    return tools


async def evict_user_mcp_tools_cache(
    user_id: str,
    server_names: List[str],
) -> None:
    """Evict cached MCP tool definitions for a user's servers.

    Call this when MCP settings are created, updated, or deleted
    so the next tool load fetches fresh definitions from the MCP server.

    Args:
        user_id: User ID whose cache entries to evict
        server_names: Server names to evict cache for
    """
    for server_name in server_names:
        cache_key = f"{user_id}:{server_name}"
        evicted = await _mcp_tools_cache.evict(cache_key)
        if evicted:
            logger.info(f"Evicted MCP tools cache: {cache_key}")


async def resolve_custom_mcp_tools(user_id: str) -> List[UserMCPTool]:
    """Resolve all available custom MCP tools for a user.

    This is a convenience function that wraps load_custom_mcp_tools_for_user()
    for use in tool resolution systems.

    Args:
        user_id: User ID to resolve tools for

    Returns:
        List of UserMCPTool instances available for the user
    """
    return await load_custom_mcp_tools_for_user(user_id=user_id)
