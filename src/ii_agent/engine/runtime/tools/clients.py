"""External client dependencies for v1 tools.

This module provides singleton instances of external clients used by tools.
This keeps the dependency graph clean - tools import from here rather than
from server modules.
"""

from ii_agent_tools.client import IIToolClient
from ii_agent_tools.client.tool_client_config import ToolClientSettings


def _get_client() -> IIToolClient:
    return IIToolClient(settings=ToolClientSettings())
