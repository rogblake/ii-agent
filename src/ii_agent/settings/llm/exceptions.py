"""LLM settings domain exceptions."""

from ii_agent.core.exceptions import NotFoundError


class LLMSettingNotFoundError(NotFoundError):
    """Raised when an LLM setting is not found or access is denied."""

    pass
