"""FastMCP-based MCP server for exposing II-Agent to external clients like ChatGPT.

This module provides backward compatibility by re-exporting from the new modular structure.
The functionality has been split into:
- models.py: Widget definitions, tool schemas, and constants
- events.py: MCPEventCollector class for event streaming
- oauth.py: OAuth 2.0 handlers and PKCE support
- agent.py: Agent execution logic
- widgets.py: Widget resource and tool handlers
- middleware.py: ASGI middleware
- server.py: MCP server creation and management
- integration.py: FastAPI integration
"""

# Re-export from models
from .models import (
    RUN_TASK_TOOL,
    IIAgentWidget,
    MAIN_WIDGET_HTML,
    WIDGET_MIME_TYPE,
    WIDGETS,
    WIDGETS_BY_ID,
    WIDGETS_BY_URI,
    get_widget_resource_meta,
    get_widget_tool_meta,
)

# Re-export from events
from .events import MCPEventCollector

# Re-export from oauth
from .oauth import (
    MCP_OAUTH_TOKEN_EXPIRY,
    health_handler,
    oauth_authorization_server_handler,
    oauth_authorize_handler,
    oauth_protected_resource_handler,
    oauth_register_handler,
    oauth_token_handler,
)

# Re-export from agent
from .agent import run_agent_internal

# Re-export from widgets
from .widgets import (
    create_call_tool_handler,
    create_read_resource_handler,
)

# Re-export from middleware
from .middleware import AcceptHeaderMiddleware

# Re-export from server
from .server import (
    create_mcp_server,
    create_mcp_server_sync,
)

# Re-export from integration
from .integration import (
    get_mcp_lifespan,
    mount_to_fastapi,
)

__all__ = [
    # Models
    "RUN_TASK_TOOL",
    "IIAgentWidget",
    "MAIN_WIDGET_HTML",
    "WIDGET_MIME_TYPE",
    "WIDGETS",
    "WIDGETS_BY_ID",
    "WIDGETS_BY_URI",
    "get_widget_resource_meta",
    "get_widget_tool_meta",
    # Events
    "MCPEventCollector",
    # OAuth
    "MCP_OAUTH_TOKEN_EXPIRY",
    "health_handler",
    "oauth_authorization_server_handler",
    "oauth_authorize_handler",
    "oauth_protected_resource_handler",
    "oauth_register_handler",
    "oauth_token_handler",
    # Agent
    "run_agent_internal",
    # Widgets
    "create_call_tool_handler",
    "create_read_resource_handler",
    # Middleware
    "AcceptHeaderMiddleware",
    # Server
    "create_mcp_server",
    "create_mcp_server_sync",
    # Integration
    "get_mcp_lifespan",
    "mount_to_fastapi",
]
