"""Custom exceptions for connectors domain."""

from ii_agent.core.exceptions import InternalError, NotFoundError, ValidationError


class ConnectorNotFoundError(NotFoundError):
    """Raised when a connector is not connected."""

    pass


class ConnectorConfigError(InternalError):
    """Raised when a connector type is invalid or misconfigured."""

    pass


class ConnectorStateError(ValidationError):
    """Raised when OAuth state verification fails."""

    pass
