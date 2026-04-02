"""FastAPI dependencies for Composio composio domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.integrations.connectors.composio.auth_config_service import AuthConfigService
from ii_agent.integrations.connectors.composio.connected_account_service import ConnectedAccountService
from ii_agent.integrations.connectors.composio.mcp_server_service import MCPServerService
from ii_agent.integrations.connectors.composio.repository import ComposioProfileRepository
from ii_agent.integrations.connectors.composio.service import ComposioService
from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService
from ii_agent.settings.mcp.dependencies import MCPSettingServiceDep


# ==================== Repository Dependencies ====================


def get_composio_profile_repository() -> ComposioProfileRepository:
    """Provide ComposioProfileRepository instance."""
    return ComposioProfileRepository()


ComposioProfileRepositoryDep = Annotated[ComposioProfileRepository, Depends(get_composio_profile_repository)]


# ==================== Service Dependencies ====================


def get_composio_service(
    mcp_setting_service: MCPSettingServiceDep,
    repo: ComposioProfileRepositoryDep,
) -> ComposioService:
    """Provide ComposioService instance with explicit repo and service injection."""
    return ComposioService(
        repo=repo,
        config=get_settings(),
        mcp_setting_service=mcp_setting_service,
        toolkit_service=ToolkitService(),
        auth_config_service=AuthConfigService(),
        connected_account_service=ConnectedAccountService(),
        mcp_server_service=MCPServerService(),
    )


ComposioServiceDep = Annotated[ComposioService, Depends(get_composio_service)]

__all__ = [
    "get_composio_profile_repository",
    "get_composio_service",
    "ComposioProfileRepositoryDep",
    "ComposioServiceDep",
]
