"""MCP Tool Loader - Loads and wraps user's custom MCP server tools.

This module provides functionality to connect to MCP servers and create
UserMCPTool wrappers for use within the v1 agent.
"""

from typing import Dict, List, Optional, Union

from fastmcp import Client, FastMCP

from ii_agent.engine.v1.tools.mcp.user_mcp_tool import UserMCPTool
from ii_agent.core.logger import logger

# Default timeout for MCP operations
DEFAULT_MCP_TIMEOUT = 60


async def load_tools_from_mcp(
    transport: Union[FastMCP, str, Dict],
    timeout: int = DEFAULT_MCP_TIMEOUT,
    mcp_server_id: Optional[str] = None,
) -> List[UserMCPTool]:
    """Load tools from an MCP (Model Context Protocol) server.

    This function establishes a connection to an MCP server, retrieves all available tools,
    and wraps them in UserMCPTool instances for use within the v1 agent. Each tool includes
    metadata such as name, description, input schema, and annotations that determine
    display properties and read-only behavior.

    Args:
        transport: The transport mechanism for connecting to the MCP server.
            Can be either:
            - FastMCP server instance for in-memory/direct connection mode
            - URL string for HTTP-based connection. Example: "http://localhost:8080/mcp"
            - MCP config dictionary. Example:
                {
                    "command": "npx",
                    "args": ["@playwright/mcp@latest", "--isolated"]
                }
        timeout: Connection timeout in seconds (default: 60)
        mcp_server_id: Optional identifier for the source MCP server

    Returns:
        List of UserMCPTool instances, each wrapping a tool from the MCP server
        with its associated metadata and execution capabilities.

    Raises:
        Various connection exceptions: If the MCP server is unreachable or returns errors.
    """
    tools: List[UserMCPTool] = []
    mcp_client = Client(transport, timeout=timeout)

    try:
        async with mcp_client:
            mcp_tools = await mcp_client.list_tools()

            for tool in mcp_tools:
                if tool.description is None:
                    logger.warning(f"Tool {tool.name} has no description, skipping")
                    continue

                # Extract annotations for display name and read-only hint
                tool_annotations = tool.annotations
                if tool_annotations is None:
                    display_name = tool.name
                    read_only = False
                else:
                    display_name = tool_annotations.title or tool.name
                    read_only = (
                        tool_annotations.readOnlyHint
                        if tool_annotations.readOnlyHint is not None
                        else False
                    )

                # Create UserMCPTool wrapper
                # Note: UserMCPTool gets mcp_client from sandbox at runtime via on_tool_start
                user_tool = UserMCPTool(
                    name=tool.name,
                    display_name=display_name,
                    description=tool.description,
                    input_schema=tool.inputSchema,
                    read_only=read_only,
                    requires_confirmation=False,
                    mcp_server_id=mcp_server_id,
                )
                tools.append(user_tool)
                logger.debug(f"Loaded MCP tool: {tool.name}")

        # Ensure stdio subprocess is terminated after listing tools.
        # MCPConfigTransport wraps the real transport, so we need to
        # reach through to the inner StdioTransport to close it.
        transport = mcp_client.transport
        if hasattr(transport, "transport"):
            await transport.transport.close()
        else:
            await transport.close()
    except Exception as e:
        logger.error(f"Failed to load tools from MCP server: {e}", exc_info=True)
        return tools

    logger.info(f"Loaded {len(tools)} tools from MCP server")
    return tools
