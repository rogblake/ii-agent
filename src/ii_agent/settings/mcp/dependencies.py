"""FastAPI dependencies for mcp_settings domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep
from ii_agent.settings.mcp.repository import MCPSettingRepository
from ii_agent.settings.mcp.service import MCPSettingService


# ==================== Repository Dependencies ====================


def get_mcp_setting_repository() -> MCPSettingRepository:
    """Provide MCPSettingRepository instance."""
    return MCPSettingRepository()


MCPSettingRepositoryDep = Annotated[MCPSettingRepository, Depends(get_mcp_setting_repository)]


# ==================== Service Dependencies ====================


def _get_mcp_setting_service(container: ContainerDep) -> MCPSettingService:
    return container.mcp_setting_service


MCPSettingServiceDep = Annotated[MCPSettingService, Depends(_get_mcp_setting_service)]
