"""External client dependencies for v1 tools.

This module provides singleton instances of external clients used by tools.
This keeps the dependency graph clean - tools import from here rather than
from server modules.
"""

from dotenv import load_dotenv

# Try to import ii_agent_tools, fallback to ii_tool if not available
try:
    from ii_agent_tools.client import IIToolClient
    from ii_agent_tools.client.tool_client_config import ToolClientSettings
except ImportError:
    # Fallback: use ii_tool client if ii_agent_tools is not available
    try:
        from ii_tool.client import IIToolClient  # type: ignore
        from ii_tool.client.tool_client_config import ToolClientSettings  # type: ignore
    except ImportError:
        # Create a mock client if neither is available
        class ToolClientSettings:  # type: ignore
            pass

        class IIToolClient:  # type: ignore
            def __init__(self, settings=None):
                pass


load_dotenv()

_tool_client: IIToolClient | None = None


def _get_client() -> IIToolClient:
    global _tool_client
    if _tool_client is None:
        _tool_client = IIToolClient(settings=ToolClientSettings())
    return _tool_client


# Global singleton - initialized once on first import
tool_client = _get_client()
