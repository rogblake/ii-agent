"""CORS middleware configuration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ii_agent_tools.app.app_config import get_settings


def configure_cors(app: FastAPI) -> None:
    """
    Configure CORS middleware with security-aware defaults.

    In production, CORS origins should be restricted to specific domains
    via the CORS_ALLOWED_ORIGINS environment variable.

    Args:
        app: FastAPI application instance
    """
    settings = get_settings()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
        max_age=3600,  # Cache preflight requests for 1 hour
    )
