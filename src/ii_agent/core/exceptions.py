"""Shared exceptions module."""

import re


def _class_name_to_error_code(name: str) -> str:
    """Convert a CamelCase class name to a snake_case error code.

    Strips trailing 'Error' or 'Exception' suffix for brevity.
    e.g. FileUploadNotFoundError -> file_upload_not_found
    """
    name = re.sub(r"(Error|Exception)$", "", name)
    # Insert underscores before uppercase letters
    code = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    code = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", code)
    return code.lower()


class IIAgentError(Exception):
    """Base for all II-Agent application errors."""

    status_code: int = 500

    def __init__(
        self,
        message: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or "An error occurred"
        self.headers = headers
        self.error_code = _class_name_to_error_code(type(self).__name__)
        super().__init__(self.message)


class NotFoundError(IIAgentError):
    """Resource not found."""

    status_code = 404


class PermissionDeniedError(IIAgentError):
    """Permission denied."""

    status_code = 403


class ValidationError(IIAgentError):
    """Validation failed."""

    status_code = 400


class ConflictError(IIAgentError):
    """Resource conflict."""

    status_code = 409


class ServiceUnavailableError(IIAgentError):
    """Service unavailable."""

    status_code = 503


class InternalError(IIAgentError):
    """Internal server error."""

    status_code = 500


class BadGatewayError(IIAgentError):
    """Bad gateway."""

    status_code = 502


class PaymentRequiredError(IIAgentError):
    """Payment required."""

    status_code = 402


class PayloadTooLargeError(IIAgentError):
    """Request payload exceeds size limit."""

    status_code = 413


class RunCancelledException(IIAgentError):
    """Exception raised when a run is cancelled.

    This is a flow-control signal, not an HTTP error. It is always caught
    explicitly before reaching the HTTP layer.
    """

    status_code = 499  # Client Closed Request (non-standard but appropriate)


class AgentRunError(InternalError):
    """Exception raised when an agent run fails.

    Note: This is distinct from ``engine.runtime.exceptions.AgentRunException``
    which is an internal flow-control signal inside the WebSocket-based
    agent loop and intentionally does **not** inherit from IIAgentError.
    """

    def __init__(self, message: str | None = "Agent Run Error") -> None:
        super().__init__(message)


class LLMProviderException(AgentRunError):
    """Exception raised when a model provider encounters an error."""

    def __init__(
        self,
        name: str,
        provider: str,
        status_code: int | None = None,
        message: str | None = "Model Provider Error",
    ) -> None:
        self.name = name
        self.provider = provider
        if status_code is not None:
            self.status_code = status_code
        super().__init__(message)
