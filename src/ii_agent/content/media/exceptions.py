"""Custom exceptions for media domain."""

from ii_agent.core.exceptions import NotFoundError


class MediaTemplateNotFoundError(NotFoundError):
    """Raised when a media template is not found."""

    pass
