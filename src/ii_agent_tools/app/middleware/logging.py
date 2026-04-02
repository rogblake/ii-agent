"""Request logging middleware with request ID tracking."""

import time
import uuid

from fastapi import HTTPException, Request, Response
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ii_agent_tools.logger import (
    bind_request_id,
    get_logger,
    reset_request_id,
)

logger = get_logger("ii_agent_tools.middleware.logging")


async def log_requests_middleware(request: Request, call_next):
    """
    Middleware to log all HTTP requests with request ID tracking.

    Features:
    - Generates or extracts X-Request-ID from headers
    - Binds request ID to logging context
    - Tracks request duration
    - Logs all requests with structured context
    - Handles validation, HTTP, and unhandled exceptions
    - Adds X-Request-ID to response headers
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = bind_request_id(request_id)
    start_time = time.perf_counter()
    response: Response | None = None

    try:
        response = await call_next(request)
    except RequestValidationError as exc:
        logger.warning(
            "Request validation failed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "errors": exc.errors(),
            },
        )
        response = await request_validation_exception_handler(request, exc)
    except HTTPException as exc:
        logger.warning(
            "HTTP error encountered",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": exc.status_code,
                "detail": exc.detail,
            },
        )
        response = await http_exception_handler(request, exc)
    except Exception:
        logger.exception(
            "Unhandled exception during request",
            extra={"method": request.method, "path": request.url.path},
        )
        response = JSONResponse(status_code=500, content={"detail": "Internal server error"})

    duration_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "request completed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code if response else 500,
            "duration_ms": round(duration_ms, 2),
        },
    )
    reset_request_id(token)

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{round(duration_ms, 2)}ms"

    return response
