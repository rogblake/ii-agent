"""Middleware for request tracing with automatic context injection."""

from __future__ import annotations

import time
import uuid
from typing import Callable

from fastapi import Request, Response

from ii_agent.core.logger import logger

SKIP_LOGGING_PATHS = [
    "/health",
]


async def request_tracing_middleware(request: Request, call_next: Callable) -> Response:
    """Middleware for request tracing with automatic context injection.

    Sets up logging context (request_id, user_id if available) that is
    automatically included in all log messages within the request scope.
    """
    # Skip noisy paths (e.g. health checks)
    if request.url.path.rstrip("/") in SKIP_LOGGING_PATHS:
        return await call_next(request)

    # Get request ID from upstream or generate new one
    request_id = (
        request.headers.get("x-request-id") or request.headers.get("x-span-id") or str(uuid.uuid4())
    )

    # Store in request state for response headers
    request.state.request_id = request_id

    # Try to get user_id from request state (set by auth middleware)
    user_id = getattr(request.state, "user_id", None)

    # Build context - all logs in this request will have these fields
    ctx: dict[str, str] = {
        "request_id": request_id,
        "http_method": request.method,
        "http_path": request.url.path,
    }
    if user_id:
        ctx["user_id"] = user_id

    # Use logger.contextualize() for scoped logging context
    with logger.contextualize(**ctx):
        start_time = time.time()

        # Log request start
        logger.info("Request started")

        try:
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000

            logger.bind(
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            ).info("Request completed")

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Span-ID"] = request_id

            return response

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.bind(
                duration_ms=round(duration_ms, 2),
                error=str(e),
            ).exception("Request failed")
            raise
