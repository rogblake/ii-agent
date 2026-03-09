"""FastAPI dependencies for sandboxes domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.engine.sandboxes.repository import SandboxRepository
from ii_agent.engine.sandboxes.service import SandboxService
from ii_agent.integrations.connectors.composio.dependencies import ComposioServiceDep
from ii_agent.settings.mcp.dependencies import MCPSettingServiceDep


# ==================== Repository Dependencies ====================


def get_sandbox_repository() -> SandboxRepository:
    """Provide SandboxRepository instance."""
    return SandboxRepository()


SandboxRepositoryDep = Annotated[SandboxRepository, Depends(get_sandbox_repository)]


# ==================== Service Dependencies ====================


def get_sandbox_service(
    sandbox_repo: SandboxRepositoryDep,
    mcp_setting_service: MCPSettingServiceDep,
    composio_service: ComposioServiceDep,
) -> SandboxService:
    """Provide SandboxService instance with explicit repo injection."""
    return SandboxService(
        sandbox_repo=sandbox_repo,
        config=get_settings(),
        mcp_setting_service=mcp_setting_service,
        composio_service=composio_service,
    )


SandboxServiceDep = Annotated[SandboxService, Depends(get_sandbox_service)]

__all__ = [
    "get_sandbox_repository",
    "get_sandbox_service",
    "SandboxRepositoryDep",
    "SandboxServiceDep",
]
