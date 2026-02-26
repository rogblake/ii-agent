"""Design domain exceptions."""

from ii_agent.core.exceptions import (
    BadGatewayError,
    NotFoundError,
    PermissionDeniedError,
    ServiceUnavailableError,
    ValidationError,
)


class DesignSessionNotFoundError(NotFoundError):
    """Raised when a session does not exist."""

    pass


class DesignSessionAccessDeniedError(PermissionDeniedError):
    """Raised when the user cannot access the target session."""

    pass


class DesignProxyHostNotAllowedError(PermissionDeniedError):
    """Raised when proxy host does not match session sandbox/public host."""

    pass


class DesignProxyFetchError(BadGatewayError):
    """Raised when proxy HTML fetch/redirect pipeline fails."""

    pass


class DesignSandboxUnavailableError(ServiceUnavailableError):
    """Raised when the sandbox required for sync cannot be resolved."""

    pass


class DesignValidationError(ValidationError):
    """Raised when the design request payload is invalid."""

    pass
