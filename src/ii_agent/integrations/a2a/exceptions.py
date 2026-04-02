"""Custom exceptions for A2A integration domain."""

from ii_agent.core.exceptions import ValidationError


class InvalidA2AAgentConfig(ValidationError):
    """Raised when an A2A agent configuration fails validation."""

    pass
