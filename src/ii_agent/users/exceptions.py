"""Custom exceptions for users domain."""

from ii_agent.core.exceptions import PermissionDeniedError
from ii_agent.auth.exceptions import AuthException


class UsersException(PermissionDeniedError):
    """Base exception for users domain."""

    pass


class WaitlistDeniedException(UsersException):
    """Raised when user is not on the waitlist during private beta."""

    pass


class UserDisabledException(AuthException):
    """Raised when a disabled user attempts to authenticate."""

    pass
