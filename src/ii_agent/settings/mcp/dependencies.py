"""FastAPI dependencies for mcp_settings domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.settings.mcp.repository import MCPSettingRepository
from ii_agent.settings.mcp.service import MCPSettingService


# ==================== Repository Dependencies ====================


def get_mcp_setting_repository() -> MCPSettingRepository:
    """Provide MCPSettingRepository instance."""
    return MCPSettingRepository()


MCPSettingRepositoryDep = Annotated[MCPSettingRepository, Depends(get_mcp_setting_repository)]


# ==================== Service Dependencies ====================


def get_mcp_setting_service(
    repo: MCPSettingRepositoryDep,
) -> MCPSettingService:
    """Provide MCPSettingService instance with explicit repo injection."""
    return MCPSettingService(repo=repo, config=get_settings())


MCPSettingServiceDep = Annotated[MCPSettingService, Depends(get_mcp_setting_service)]


__all__ = [
    "get_mcp_setting_repository",
    "get_mcp_setting_service",
    "MCPSettingRepositoryDep",
    "MCPSettingServiceDep",
]
