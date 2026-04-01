"""Middleware and exception handlers for unhandled errors."""

from __future__ import annotations

from typing import Callable

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse

from ii_agent.core.exceptions import IIAgentError, NotFoundException, PermissionException
from ii_agent.core.logger import logger


async def exception_logging_middleware(
    request: Request, call_next: Callable
) -> Response:
    """Middleware to handle and log unhandled exceptions."""
    try:
        return await call_next(request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    except Exception:
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=500, content={"detail": "Internal Server Error"}
        )


async def permission_exception_handler(
    request: Request, exc: PermissionException
) -> JSONResponse:
    """Exception handler for PermissionException."""
    logger.warning(f"Permission denied: {exc}")
    return JSONResponse(status_code=403, content={"detail": str(exc)})


async def not_found_exception_handler(
    request: Request, exc: NotFoundException
) -> JSONResponse:
    """Exception handler for NotFoundException."""
    logger.warning(f"Not found: {exc}")
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def ii_agent_error_handler(
    request: Request, exc: IIAgentError
) -> JSONResponse:
    """Exception handler for IIAgentError and subclasses."""
    logger.warning(f"IIAgentError: {exc}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "error_code": exc.error_code},
        headers=exc.headers,
    )
