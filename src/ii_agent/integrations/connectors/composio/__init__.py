"""Composio integration module for II-Agent.

Provides integration with Composio (https://composio.dev/) for connecting
to 100+ external services like Gmail, Google Calendar, Slack, Notion, etc.

Import patterns:
    from ii_agent.integrations.connectors.composio import ComposioService, router
    from ii_agent.integrations.connectors.composio import ComposioService
    from ii_agent.integrations.connectors.composio import ComposioProfileInfo
"""

from .client import ComposioClient
from .cache_service import ComposioCacheService
from .toolkit_service import ToolkitService, ToolkitInfo, CategoryInfo, DetailedToolkitInfo
from .auth_config_service import AuthConfigService, AuthConfig
from .connected_account_service import ConnectedAccountService, ConnectedAccount
from .mcp_server_service import MCPServerService, MCPServer
from .repository import ComposioProfileRepository
from .service import ComposioService
from .dependencies import ComposioProfileRepositoryDep, ComposioServiceDep
from .router import router
from .schemas import (
    ComposioProfileInfo,
    ConnectToolkitRequest,
    ConnectToolkitResponse,
    CompleteOAuthRequest,
    ToolkitStatusResponse,
    ProfileMCPConfigResponse,
    SyncProfileResponse,
    UpdateProfileToolsRequest,
)

__all__ = [
    # Client
    "ComposioClient",
    # Cache
    "ComposioCacheService",
    # Toolkit discovery
    "ToolkitService",
    "ToolkitInfo",
    "CategoryInfo",
    "DetailedToolkitInfo",
    # Auth config
    "AuthConfigService",
    "AuthConfig",
    # Connected accounts
    "ConnectedAccountService",
    "ConnectedAccount",
    # MCP servers
    "MCPServerService",
    "MCPServer",
    # Repository
    "ComposioProfileRepository",
    # Service
    "ComposioService",
    # Dependencies (Dep aliases)
    "ComposioProfileRepositoryDep",
    "ComposioServiceDep",
    # Router
    "router",
    # Schemas
    "ComposioProfileInfo",
    "ConnectToolkitRequest",
    "ConnectToolkitResponse",
    "CompleteOAuthRequest",
    "ToolkitStatusResponse",
    "ProfileMCPConfigResponse",
    "SyncProfileResponse",
    "UpdateProfileToolsRequest",
]
