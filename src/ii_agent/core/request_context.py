"""Request context management for distributed tracing.

This module provides request ID propagation through the entire request lifecycle using
Python's contextvars. This enables end-to-end tracing from WebSocket/HTTP entry points
through to downstream services like the sandbox server.
"""

import uuid
from contextvars import ContextVar
from typing import Optional

# Context variable to store request ID across async calls
_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def generate_request_id() -> str:
    """Generate a new UUID-based request ID."""
    return str(uuid.uuid4())


def set_request_id(request_id: Optional[str] = None) -> str:
    """Set the request ID in the current context.

    Args:
        request_id: The request ID to set. If None, generates a new one.

    Returns:
        The request ID that was set
    """
    if request_id is None:
        request_id = generate_request_id()

    _request_id_var.set(request_id)
    return request_id


def get_request_id() -> Optional[str]:
    """Get the request ID from the current context.

    Returns:
        The current request ID, or None if not set
    """
    return _request_id_var.get()


def get_or_generate_request_id() -> str:
    """Get the current request ID, or generate a new one if not set.

    Returns:
        The current or newly generated request ID
    """
    request_id = get_request_id()
    if request_id is None:
        request_id = set_request_id()
    return request_id


def clear_request_id() -> None:
    """Clear the request ID from the current context."""
    _request_id_var.set(None)
