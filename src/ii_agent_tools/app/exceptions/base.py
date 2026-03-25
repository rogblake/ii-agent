"""Base exception classes for the application."""


class ServiceError(Exception):
    """Base exception for service-level errors."""

    def __init__(
        self, message: str, status_code: int = 500, details: dict | None = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(ServiceError):
    """Exception for validation errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, status_code=400, details=details)


class AuthenticationError(ServiceError):
    """Exception for authentication errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, status_code=401, details=details)


class AuthorizationError(ServiceError):
    """Exception for authorization errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, status_code=403, details=details)


class NotFoundError(ServiceError):
    """Exception for resource not found errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, status_code=404, details=details)


class RateLimitError(ServiceError):
    """Exception for rate limit errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, status_code=429, details=details)


class ExternalServiceError(ServiceError):
    """Exception for external service errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, status_code=503, details=details)
