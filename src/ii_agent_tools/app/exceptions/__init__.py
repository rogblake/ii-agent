"""Exception handling for the application."""

from ii_agent_tools.app.exceptions.base import (
    AuthenticationError,
    AuthorizationError,
    ExternalServiceError,
    NotFoundError,
    RateLimitError,
    ServiceError,
    ValidationError,
)
from ii_agent_tools.app.exceptions.handlers import (
    generic_error_handler,
    service_error_handler,
    validation_error_handler,
)

__all__ = [
    # Base exceptions
    "ServiceError",
    "ValidationError",
    "AuthenticationError",
    "AuthorizationError",
    "NotFoundError",
    "RateLimitError",
    "ExternalServiceError",
    # Handlers
    "service_error_handler",
    "validation_error_handler",
    "generic_error_handler",
]
