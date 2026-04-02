"""MCP Server module for exposing II-Agent to external clients like ChatGPT."""

from .wellknown import wellknown_router as mcp_wellknown_router
from .integration import get_mcp_lifespan, mount_to_fastapi
from .server import create_mcp_server_sync

__all__ = [
    "mcp_wellknown_router",
    "get_mcp_lifespan",
    "mount_to_fastapi",
    "create_mcp_server_sync",
]
