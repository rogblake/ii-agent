"""Application bootstrap package for the FastAPI + Socket.IO server."""

from __future__ import annotations

import logging

import socketio
from fastapi import FastAPI

from ii_agent.core.config.settings import get_settings
from ii_agent.core.redis import get_session_manager

from .health import health_router
from .lifespan import create_lifespan

logger = logging.getLogger(__name__)

PROD_ENV = {"production", "prod"}


def create_app() -> socketio.ASGIApp:
    """Create and configure the FastAPI application with Socket.IO integration."""
    from .middleware import configure_middleware
    from .routers import include_routers

    settings = get_settings()
    docs_enabled = settings.environment not in PROD_ENV

    # Socket.IO server — must exist before lifespan (wraps the ASGI app)
    sio = socketio.AsyncServer(
        async_mode="asgi",
        cors_allowed_origins="*",
        ping_timeout=300,
        ping_interval=30,
        max_http_buffer_size=10 * 1024 * 1024,
        client_manager=get_session_manager(),
    )

    app = FastAPI(
        title="Agent Socket.IO API",
        lifespan=create_lifespan(sio),
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    configure_middleware(app, settings)
    include_routers(app)

    app.state.sio = sio

    return socketio.ASGIApp(sio, app)


__all__ = [
    "create_app",
    "health_router",
]
