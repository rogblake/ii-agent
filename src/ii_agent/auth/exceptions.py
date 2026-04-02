"""Custom exceptions for auth domain."""

from ii_agent.core.exceptions import IIAgentError, ConflictError, InternalError


class AuthException(IIAgentError):
    """Base exception for auth domain."""

    status_code = 401

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message, headers={"WWW-Authenticate": "Bearer"})


class InvalidCredentialsException(AuthException):
    """Raised when credentials are invalid."""

    pass


class UserNotFoundException(AuthException):
    """Raised when user is not found."""

    pass


class UserAlreadyExistsException(ConflictError):
    """Raised when user already exists."""

    pass


class TokenExpiredException(AuthException):
    """Raised when token has expired."""

    pass


class InvalidTokenException(AuthException):
    """Raised when token is invalid."""

    pass


class OIDCConfigError(InternalError):
    """Raised when OIDC configuration is missing or invalid."""

    pass
