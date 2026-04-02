"""Storybook domain exceptions."""

from ii_agent.core.exceptions import InternalError, NotFoundError, PermissionDeniedError


class StorybookNotFoundError(NotFoundError):
    """Raised when a storybook is not found."""

    pass


class StorybookAccessDeniedError(PermissionDeniedError):
    """Raised when access to a storybook is denied."""

    pass


class StorybookPageNotFoundError(NotFoundError):
    """Raised when a storybook page is not found."""

    pass


class StorybookExportError(InternalError):
    """Raised when PDF/PNG export fails."""

    pass


class StorybookVersionError(InternalError):
    """Raised when storybook version creation fails."""

    pass
