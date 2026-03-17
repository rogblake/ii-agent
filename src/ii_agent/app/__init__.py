"""Application bootstrap package for the FastAPI + Socket.IO server."""

from __future__ import annotations

import logging

from ii_agent.core.config.settings import get_settings

from .health import health_router
import socketio
from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Module-level Socket.IO instance (set during app creation)
sio: socketio.AsyncServer | None = None

# Suppress noisy MCP session crash logs caused by expected client disconnections.
logging.getLogger("mcp.server.streamable_http_manager").setLevel(logging.CRITICAL)


def create_lifespan():
    """Return the application lifespan context manager factory."""
    from .lifespan import create_lifespan as _create_lifespan

    return _create_lifespan()


def mount_fastmcp_server(app: FastAPI, mount_path: str = "/mcp") -> None:
    """Mount the FastMCP server for ChatGPT integration."""
    from .mounts import mount_fastmcp_server as _mount_fastmcp_server

    _mount_fastmcp_server(app, mount_path)


def mount_a2a_server(app: FastAPI, mount_path: str = "/a2a") -> None:
    """Mount the embedded A2A server as a sub-application."""
    from .mounts import mount_a2a_server as _mount_a2a_server

    _mount_a2a_server(app, mount_path)


def create_app():
    """Create and configure the FastAPI application with Socket.IO integration."""
    from .middleware import configure_exception_handlers, configure_middleware
    from .routers import include_routers

    settings = get_settings()
    docs_enabled = settings.environment != "production"

    app = FastAPI(
        title="Agent Socket.IO API",
        lifespan=create_lifespan(),
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    configure_middleware(app, settings)
    configure_exception_handlers(app)

    app.state.workspace = settings.workspace_path
    include_routers(app)

    global sio
    try:
        from ii_agent.agent.socket.socketio import SocketIOManager
    except Exception as exc:  # pragma: no cover - defensive bootstrap fallback
        sio = None
        app.state.sio = None
        logger.warning(
            "Socket.IO manager unavailable during app creation: %s",
            exc,
            exc_info=True,
        )
        return app

    from ii_agent.core.redis import session_manager

    sio = socketio.AsyncServer(
        async_mode="asgi",
        cors_allowed_origins="*",
        ping_timeout=300,
        ping_interval=30,
        max_http_buffer_size=10 * 1024 * 1024,
        client_manager=session_manager,
    )

    sio_manager = SocketIOManager(sio)
    app.state.sio_manager = sio_manager
    app.state.sio = sio
    return socketio.ASGIApp(sio, app)


__all__ = [
    "create_app",
    "create_lifespan",
    "health_router",
    "mount_a2a_server",
    "mount_fastmcp_server",
    "sio",
]
