"""MCP settings domain exceptions."""

from ii_agent.core.exceptions import NotFoundError, ValidationError


class MCPSettingNotFoundError(NotFoundError):
    """Raised when an MCP setting is not found or access is denied."""

    pass


class MCPOAuthError(ValidationError):
    """Raised when OAuth token exchange fails."""

    pass
