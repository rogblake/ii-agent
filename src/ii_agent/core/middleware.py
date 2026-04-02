"""Middleware for FastAPI including request tracing and exception handling."""

import logging
import time
import traceback
from typing import Callable
from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from ii_agent.core.exceptions import IIAgentError
from ii_agent.core.request_context import set_request_id


logger = logging.getLogger(__name__)


async def request_tracing_middleware(
    request: Request, call_next: Callable
) -> Response:
    """Middleware to generate and propagate request IDs for distributed tracing.

    Args:
        request: The incoming request
        call_next: The next middleware in the chain

    Returns:
        Response with request ID in headers
    """
    # Use upstream request ID if present, otherwise generate new one
    request_id = (
        request.headers.get("x-request-id")
        or request.headers.get("x-span-id")
        or None
    )
    request_id = set_request_id(request_id)

    # Start timer for request duration
    start_time = time.time()

    # Log request with upstream indicator
    upstream_indicator = "(upstream)" if request.headers.get("x-request-id") else "(generated)"
    logger.info(
        f"[{request_id}] {upstream_indicator} {request.method} {request.url.path}"
    )

    try:
        response = await call_next(request)

        # Calculate duration
        duration = time.time() - start_time

        # Log response
        logger.info(
            f"[{request_id}] {request.method} {request.url.path} - "
            f"Status: {response.status_code} - Duration: {duration:.3f}s"
        )

        # Add request ID to response headers for correlation
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Span-ID"] = request_id

        return response

    except IIAgentError:
        # Don't log here — ii_agent_error_handler logs these with proper
        # status-code awareness.  Re-raise so the registered handler runs.
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(
            f"[{request_id}] {request.method} {request.url.path} - "
            f"Error: {str(e)} - Duration: {duration:.3f}s",
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": "Internal Server Error"},
            headers={"X-Request-ID": request_id, "X-Span-ID": request_id},
        )


async def exception_logging_middleware(
    request: Request, call_next: Callable
) -> Response:
    """Middleware to log unhandled exceptions.

    Args:
    ----
        request (Request): The incoming request.
        call_next (Callable): The next middleware in the chain.

    Returns:
    -------
        Response: The response to the incoming request.

    """
    try:
        response = await call_next(request)
        return response
    except IIAgentError:
        # Let the registered app.exception_handler(IIAgentError) handle this
        raise
    except HTTPException as exc:
        if exc.status_code >= 500:
            logger.error(
                f"[{exc.status_code}] {request.method} {request.url.path}: {exc.detail}",
                exc_info=True,
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    except Exception as _:
        logger.error(traceback.format_exc(), exc_info=True)
        return JSONResponse(
            status_code=500, content={"detail": "Internal Server Error"}
        )


async def ii_agent_error_handler(
    request: Request, exc: IIAgentError
) -> JSONResponse:
    """Global exception handler for all IIAgentError subclasses.

    Automatically maps exception status_code to HTTP response status.
    """
    status_code = getattr(exc, "status_code", 500) or 500
    error_code = getattr(exc, "error_code", "internal_error")

    if status_code >= 500:
        logger.error(
            f"[{status_code}] {request.method} {request.url.path}: {exc}",
            exc_info=True,
        )
    elif status_code in (401, 403):
        logger.warning(
            f"[{status_code}] {request.method} {request.url.path}: {exc}",
        )
    else:
        # 400, 404, 409, 413, etc. — useful for debugging without spamming
        logger.debug(
            f"[{status_code}] {request.method} {request.url.path}: {exc}",
        )

    headers = getattr(exc, "headers", None)
    return JSONResponse(
        status_code=status_code,
        content={"error": error_code, "detail": exc.message},
        headers=headers,
    )
