"""Slide design domain exceptions."""

from ii_agent.core.exceptions import NotFoundError


class DesignSlideNotFoundError(NotFoundError):
    """Raised when one or more target slides are missing."""

    pass
