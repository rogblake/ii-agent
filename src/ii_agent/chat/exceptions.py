"""Chat domain exceptions."""

from typing import Optional

from ii_agent.core.exceptions import PayloadTooLargeError, ValidationError


class ModelNotFoundError(ValidationError):
    """Raised when a requested LLM model is not found.

    Uses 400 (not 404) to avoid confusion with route-not-found.
    """

    pass


class AnthropicImageTooLargeError(PayloadTooLargeError):
    """Raised when an inline image exceeds Anthropic's 5 MB limit."""

    def __init__(self, size_bytes: Optional[int] = None):
        self.size_bytes = size_bytes
        suffix = f" ({size_bytes} bytes)" if size_bytes is not None else ""
        super().__init__(f"Image exceeds Anthropic's 5 MB inline limit{suffix}")
