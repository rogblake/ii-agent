"""MCP configuration domain module."""

from .dependencies import MCPSettingRepositoryDep, MCPSettingServiceDep
from .exceptions import MCPOAuthError, MCPSettingNotFoundError
from .models import MCPSetting
from .repository import MCPSettingRepository
from .router import router
from .service import MCPSettingService

__all__ = [
    # Models
    "MCPSetting",
    # Repository
    "MCPSettingRepository",
    # Service
    "MCPSettingService",
    # Dependencies
    "MCPSettingRepositoryDep",
    "MCPSettingServiceDep",
    # Exceptions
    "MCPOAuthError",
    "MCPSettingNotFoundError",
    # Router
    "router",
]
