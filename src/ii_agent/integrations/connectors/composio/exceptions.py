"""Composio connector domain exceptions."""

from ii_agent.core.exceptions import NotFoundError, ValidationError


class ComposioProfileNotFoundError(NotFoundError):
    """Raised when a Composio profile is not found."""

    pass


class ComposioToolkitNotFoundError(NotFoundError):
    """Raised when a Composio toolkit is not found."""

    pass


class ComposioOAuthError(ValidationError):
    """Raised when a Composio OAuth flow fails."""

    pass
