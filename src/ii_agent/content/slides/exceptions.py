"""Slides domain exceptions."""

from ii_agent.core.exceptions import NotFoundError, PermissionDeniedError


class SlideNotFoundError(NotFoundError):
    """Raised when slides are not found or access is denied."""

    pass


class SessionAccessDeniedError(PermissionDeniedError):
    """Raised when session access is denied."""

    pass
