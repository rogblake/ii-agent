"""Exception handlers for FastAPI application."""

from fastapi import Request
from fastapi.responses import JSONResponse

from ii_agent_tools.app.exceptions.base import ServiceError
from ii_agent_tools.logger import get_logger

logger = get_logger(__name__)


async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    """
    Handle ServiceError and its subclasses.

    This centralizes error handling for all service-level exceptions,
    ensuring consistent error responses and logging.

    Args:
        request: The FastAPI request
        exc: The ServiceError exception

    Returns:
        JSONResponse with error details
    """
    logger.error(
        f"Service error: {exc.message}",
        extra={
            "status_code": exc.status_code,
            "details": exc.details,
            "method": request.method,
            "path": request.url.path,
        },
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "error_type": exc.__class__.__name__,
            **exc.details,
        },
    )


async def validation_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """
    Handle ValueError exceptions as validation errors.

    Maps ValueError to 400 Bad Request responses.

    Args:
        request: The FastAPI request
        exc: The ValueError exception

    Returns:
        JSONResponse with validation error details
    """
    logger.warning(
        f"Validation error: {str(exc)}",
        extra={
            "method": request.method,
            "path": request.url.path,
        },
    )

    return JSONResponse(
        status_code=400,
        content={
            "detail": str(exc),
            "error_type": "ValidationError",
        },
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle unexpected exceptions.

    Logs the full exception and returns a generic error response
    to avoid leaking implementation details.

    Args:
        request: The FastAPI request
        exc: The exception

    Returns:
        JSONResponse with generic error message
    """
    logger.exception(
        "Unhandled exception",
        extra={
            "method": request.method,
            "path": request.url.path,
            "exception_type": type(exc).__name__,
        },
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_type": "InternalServerError",
        },
    )
