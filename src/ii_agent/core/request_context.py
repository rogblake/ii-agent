"""Request context management for distributed tracing and logging.

This module provides request-scoped context propagation through the entire request lifecycle
using Python's contextvars. This enables:
- End-to-end tracing from WebSocket/HTTP entry points through to downstream services
- Automatic inclusion of context (user_id, session_id, etc.) in all log entries
- Correlation of logs across async operations

Usage:
    # Use context manager (recommended)
    async with request_scope(user_id="u123", session_id="sess-456"):
        logger.info("Processing")  # Auto-includes user_id, session_id
        await do_work()
    # Context automatically cleared

    # Or set manually
    set_context(user_id="u123")
    logger.info("Processing")
    clear_context()
"""

import uuid
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Iterator, Optional


@dataclass
class RequestContext:
    """Container for request-scoped context information."""

    request_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    agent_id: Optional[str] = None
    model_id: Optional[str] = None
    # Additional metadata that can be set dynamically
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dict, excluding None values."""
        result = {}
        if self.request_id:
            result["request_id"] = self.request_id
        if self.user_id:
            result["user_id"] = self.user_id
        if self.session_id:
            result["session_id"] = self.session_id
        if self.run_id:
            result["run_id"] = self.run_id
        if self.agent_id:
            result["agent_id"] = self.agent_id
        if self.model_id:
            result["model_id"] = self.model_id
        if self.extra:
            result.update(self.extra)
        return result


# Context variable storing the full request context
_context_var: ContextVar[RequestContext] = ContextVar(
    "request_context", default=RequestContext()
)


def generate_request_id() -> str:
    """Generate a new UUID-based request ID."""
    return str(uuid.uuid4())


def get_context() -> RequestContext:
    """Get the current request context.

    Returns:
        The current RequestContext (never None, returns empty context if not set)
    """
    return _context_var.get()


def set_context(
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    model_id: Optional[str] = None,
    **extra: Any,
) -> RequestContext:
    """Set the request context with provided values.

    Any values not provided will be preserved from the existing context.

    Args:
        request_id: Request/trace ID for correlation
        user_id: Authenticated user ID
        session_id: Chat/workspace session ID
        run_id: Agent run/task ID
        agent_id: Agent instance ID
        model_id: LLM model being used
        **extra: Additional key-value pairs to include

    Returns:
        The updated RequestContext
    """
    current = _context_var.get()

    # Create new context, preserving existing values if not overwritten
    new_context = RequestContext(
        request_id=request_id if request_id is not None else current.request_id,
        user_id=user_id if user_id is not None else current.user_id,
        session_id=session_id if session_id is not None else current.session_id,
        run_id=run_id if run_id is not None else current.run_id,
        agent_id=agent_id if agent_id is not None else current.agent_id,
        model_id=model_id if model_id is not None else current.model_id,
        extra={**current.extra, **extra},
    )

    _context_var.set(new_context)
    return new_context


def clear_context() -> None:
    """Clear all context values."""
    _context_var.set(RequestContext())


# Convenience functions for backward compatibility and common operations


def set_request_id(request_id: Optional[str] = None) -> str:
    """Set the request ID in the current context.

    Args:
        request_id: The request ID to set. If None, generates a new one.

    Returns:
        The request ID that was set
    """
    if request_id is None:
        request_id = generate_request_id()

    set_context(request_id=request_id)
    return request_id


def get_request_id() -> Optional[str]:
    """Get the request ID from the current context."""
    return get_context().request_id


def get_or_generate_request_id() -> str:
    """Get the current request ID, or generate a new one if not set."""
    request_id = get_request_id()
    if request_id is None:
        request_id = set_request_id()
    return request_id


def clear_request_id() -> None:
    """Clear the request ID from the current context."""
    ctx = get_context()
    set_context(
        request_id=None,
        user_id=ctx.user_id,
        session_id=ctx.session_id,
        run_id=ctx.run_id,
        agent_id=ctx.agent_id,
        model_id=ctx.model_id,
    )


# Additional convenience setters


def set_user_id(user_id: str) -> None:
    """Set the user ID in the current context."""
    set_context(user_id=user_id)


def set_session_id(session_id: str) -> None:
    """Set the session ID in the current context."""
    set_context(session_id=session_id)


def set_run_id(run_id: str) -> None:
    """Set the run/task ID in the current context."""
    set_context(run_id=run_id)


def set_agent_id(agent_id: str) -> None:
    """Set the agent ID in the current context."""
    set_context(agent_id=agent_id)


def set_model_id(model_id: str) -> None:
    """Set the model ID in the current context."""
    set_context(model_id=model_id)


# Context managers for clean scoped context


@asynccontextmanager
async def request_scope(
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    model_id: Optional[str] = None,
    **extra: Any,
) -> AsyncIterator[RequestContext]:
    """
    Async context manager for request-scoped context.

    Automatically sets context on entry and clears on exit.
    Use this in async handlers (socketio, FastAPI endpoints).

    Usage:
        async with request_scope(user_id="u123", session_id="s456"):
            logger.info("Processing")  # has user_id, session_id
            await do_work()
        # context cleared automatically
    """
    # Generate request_id if not provided
    if request_id is None:
        request_id = generate_request_id()

    ctx = set_context(
        request_id=request_id,
        user_id=user_id,
        session_id=session_id,
        run_id=run_id,
        agent_id=agent_id,
        model_id=model_id,
        **extra,
    )
    try:
        yield ctx
    finally:
        clear_context()


@contextmanager
def request_scope_sync(
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    model_id: Optional[str] = None,
    **extra: Any,
) -> Iterator[RequestContext]:
    """
    Sync context manager for request-scoped context.

    Use this in sync code paths.
    """
    if request_id is None:
        request_id = generate_request_id()

    ctx = set_context(
        request_id=request_id,
        user_id=user_id,
        session_id=session_id,
        run_id=run_id,
        agent_id=agent_id,
        model_id=model_id,
        **extra,
    )
    try:
        yield ctx
    finally:
        clear_context()
