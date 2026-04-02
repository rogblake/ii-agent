"""Project domain exceptions."""

from ii_agent.core.exceptions import NotFoundError


class ProjectNotFoundError(NotFoundError):
    """Raised when a project is not found or access is denied."""

    pass
