"""MCP server creation and management for MCP SSE server."""

import asyncio
import logging
from copy import deepcopy
from typing import List, Optional

import fastmcp
from fastmcp import FastMCP
from mcp import types as mcp_types

from .models import (
    RUN_TASK_TOOL,
    REFRESH_SESSION_STATUS_TOOL,
    WIDGET_MIME_TYPE,
    WIDGETS,
    WIDGETS_BY_ID,
    get_widget_resource_meta,
    get_widget_tool_meta,
)
from .widgets import create_call_tool_handler, create_read_resource_handler

logger = logging.getLogger(__name__)

# Global MCP server instance
_mcp_server: Optional[FastMCP] = None


async def create_mcp_server() -> FastMCP:
    """Create and configure the FastMCP server for ChatGPT/OpenAI integration."""
    fastmcp.settings.stateless_http = True
    mcp = FastMCP(
        name="II-Agent MCP Server",
        instructions="This server provides access to II-Agent, an AI assistant that can help with various tasks including coding, research, and general assistance.",
    )

    @mcp._mcp_server.list_tools()
    async def _list_tools() -> List[mcp_types.Tool]:
        """Return available tools."""
        return [
            mcp_types.Tool(
                name="run_task",
                description=RUN_TASK_TOOL.description,
                inputSchema=deepcopy(RUN_TASK_TOOL.inputSchema),
                _meta=get_widget_tool_meta(WIDGETS_BY_ID.get("run_task")),
            ),
            mcp_types.Tool(
                name="refresh_session_status",
                description=REFRESH_SESSION_STATUS_TOOL.description,
                inputSchema=deepcopy(REFRESH_SESSION_STATUS_TOOL.inputSchema),
                _meta=get_widget_tool_meta(WIDGETS_BY_ID.get("refresh_session_status"), visibility="private"),
            )
        ]

    @mcp._mcp_server.list_resources()
    async def _list_resources() -> List[mcp_types.Resource]:
        """Return available widget resources."""
        return [
            mcp_types.Resource(
                name=widget.title,
                uri=widget.template_uri,
                description=f"Widget for {widget.title}",
                mimeType=WIDGET_MIME_TYPE,
                _meta=get_widget_resource_meta(widget),
            )
            for widget in WIDGETS
        ]

    @mcp._mcp_server.list_resource_templates()
    async def _list_resource_templates() -> List[mcp_types.ResourceTemplate]:
        """Return available resource templates."""
        return [
            mcp_types.ResourceTemplate(
                name=widget.title,
                uriTemplate=widget.template_uri,
                description=f"Template for {widget.title}",
                mimeType=WIDGET_MIME_TYPE,
                _meta=get_widget_resource_meta(widget),
            )
            for widget in WIDGETS
        ]

    mcp._mcp_server.request_handlers[mcp_types.CallToolRequest] = create_call_tool_handler(mcp)
    mcp._mcp_server.request_handlers[mcp_types.ReadResourceRequest] = create_read_resource_handler()

    logger.info("Registered custom MCP request handlers for OpenAI compatibility")

    return mcp


def create_mcp_server_sync() -> Optional[FastMCP]:
    """Create MCP server synchronously for use during FastAPI app creation.

    Returns the FastMCP server instance. The caller should use mount_to_fastapi()
    to properly integrate it with FastAPI.
    """
    global _mcp_server

    if _mcp_server is not None:
        return _mcp_server

    async def create():
        global _mcp_server
        _mcp_server = await create_mcp_server()
        return _mcp_server

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            mcp_server = loop.run_until_complete(create())
        finally:
            loop.close()

        logger.info("Created FastMCP server")
        return mcp_server

    except Exception as e:
        logger.error(f"Failed to create MCP server: {e}", exc_info=True)
        return None
