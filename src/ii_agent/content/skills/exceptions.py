"""Skills domain exceptions."""

from ii_agent.core.exceptions import ConflictError, NotFoundError, ValidationError


class SkillNotFoundError(NotFoundError):
    """Raised when a skill is not found or access is denied."""

    pass


class SkillAlreadyExistsError(ConflictError):
    """Raised when a skill with the same name already exists."""

    pass


class BuiltinSkillDeleteError(ValidationError):
    """Raised when trying to delete a builtin skill."""

    pass
