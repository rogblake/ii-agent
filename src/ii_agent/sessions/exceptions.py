"""Sessions domain exceptions."""

from ii_agent.core.exceptions import NotFoundError, ValidationError


class SessionNotFoundError(NotFoundError):
    """Raised when a session is not found or access is denied."""

    pass


class SessionValidationError(ValidationError):
    """Raised when a session ID is invalid."""

    pass
