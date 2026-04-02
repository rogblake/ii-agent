"""Chat domain exceptions."""

from typing import Optional

from ii_agent.core.exceptions import NotFoundError, PayloadTooLargeError


class ModelNotFoundError(NotFoundError):
    """Raised when a requested LLM model is not found."""

    pass


class AnthropicImageTooLargeError(PayloadTooLargeError):
    """Raised when an inline image exceeds Anthropic's 5 MB limit."""

    def __init__(self, size_bytes: Optional[int] = None):
        self.size_bytes = size_bytes
        suffix = f" ({size_bytes} bytes)" if size_bytes is not None else ""
        super().__init__(
            f"Image exceeds Anthropic's 5 MB inline limit{suffix}"
        )
