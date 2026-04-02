import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
import socketio
from fastapi.middleware.gzip import GZipMiddleware
from ii_agent.core.redis import close_redis, session_manager
from ii_agent.core.exceptions import IIAgentError
from ii_agent.core.middleware import (
    request_tracing_middleware,
    exception_logging_middleware,
    ii_agent_error_handler,
)

from ii_agent.auth import router as auth_router
from ii_agent.auth.users.router import router as users_router
from ii_agent.sessions.router import router as sessions_router
from ii_agent.billing import router as billing_router
from ii_agent.sessions.wishlist import router as wishlist_router
from ii_agent.integrations.connectors import router as connectors_router
from ii_agent.files.router import router as files_router
from ii_agent.content.storybook.router import router as storybook_router
from ii_agent.settings.llm import router as llm_settings_router
from ii_agent.settings.mcp import router as mcp_settings_router
from ii_agent.content.skills import router as skills_settings_router
# from ii_agent.engine.agents.beta.enhance_prompt import router as enhance_prompt_router
from ii_agent.chat.router import router as chat_router
from ii_agent.engine.v1.api import v1_router
from ii_agent.projects.router import router as project_router
from ii_agent.projects.subdomains import router as subdomains_router
from ii_agent.content.media import router as media_router
from ii_agent.content.media.router import templates_router as media_templates_router
from ii_agent.content.media.router import tools_router as media_tools_router
# from ii_agent.integrations.mcp_sse import mcp_wellknown_router, get_mcp_lifespan
from ii_agent.content.slides import router as slides_router
from ii_agent.content.slides import template_router as slide_templates_router
from ii_agent.billing.credits.router import router as credits_router
from ii_agent.core.config.settings import get_settings
from ii_agent.core.container import ServiceContainer
from ii_agent.realtime.socket.socketio import SocketIOManager

logger = logging.getLogger(__name__)

# Module-level Socket.IO instance (set during app creation)
# Access via: from ii_agent.app import sio
sio: socketio.AsyncServer | None = None

# Suppress noisy MCP session crash logs caused by expected client disconnections
# These ClosedResourceError exceptions occur when clients disconnect before the server
# finishes processing (e.g., timeout, user cancellation) - this is normal behavior
logging.getLogger("mcp.server.streamable_http_manager").setLevel(logging.CRITICAL)


health_router = APIRouter()


@health_router.get("/health")
async def health_check():
    return {"status": "ok"}


def create_lifespan():
    """Create lifespan context manager with MCP support.

    This factory function is needed because we need to access get_mcp_lifespan()
    after mount_to_fastapi() has been called (which sets up the _mcp_app global).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage application lifespan events.

        Services are initialized as module-level singletons in their respective
        service modules (e.g., billing_service in billing/service.py).

        GCP secrets are loaded automatically during Settings construction via
        GCPSecretManagerSource — no manual loading needed here.
        """
        # Create centralized service container
        container = ServiceContainer.create()
        app.state.container = container

        # Get MCP lifespan if available (must be called after mount_to_fastapi)
        # mcp_lifespan_fn = get_mcp_lifespan()
        # mcp_lifespan_ctx = None

        # Initialize Socket.IO manager asynchronously
        sio_manager: SocketIOManager
        if hasattr(app.state, "sio_manager"):
            sio_manager = app.state.sio_manager
            sio_manager.set_container(container)
            await sio_manager.init()
            logger.info("Socket.IO manager initialized during startup")

        # Start MCP lifespan first to initialize task group
        # if mcp_lifespan_fn is not None:
        #     mcp_lifespan_ctx = mcp_lifespan_fn(app)
        #     await mcp_lifespan_ctx.__aenter__()
        #     logger.info("FastMCP lifespan initialized")

        # Store settings in app state
        settings = get_settings()
        app.state.settings = settings

        # Run database migrations unless explicitly skipped
        if not os.getenv("II_AGENT_SKIP_MIGRATIONS", "").lower() in ("1", "true", "yes"):
            from ii_agent.core.db.manager import run_migrations
            run_migrations()
            logger.info("Database migrations applied")
        else:
            logger.info("Skipping database migrations (II_AGENT_SKIP_MIGRATIONS)")

        # Startup: Initialize admin LLM settings and builtin skills
        from ii_agent.settings.llm.seeding import ensure_admin_llm_settings_seeded
        from ii_agent.content.skills.seeding import ensure_builtin_skills_synced
        from ii_agent.scripts.tasks import start_scheduler

        try:
            await ensure_admin_llm_settings_seeded()
            await ensure_builtin_skills_synced()
        except Exception as e:
            logger.error(f"Failed to initialize admin LLM settings during startup: {e}")

        start_scheduler()

        yield

        # Shutdown
        from ii_agent.scripts.tasks import shutdown_scheduler

        if sio_manager:
            await sio_manager.shutdown()
            logger.info("Socket.IO manager shut down")
        await close_redis()
        shutdown_scheduler()

        # Shutdown MCP lifespan
        # if mcp_lifespan_ctx is not None:
        #     await mcp_lifespan_ctx.__aexit__(None, None, None)
        #     logger.info("FastMCP lifespan shut down")

    return lifespan


def create_app():
    """Create and configure the FastAPI application with Socket.IO integration.

    Returns:
        socketio.ASGIApp: Configured Socket.IO application instance
    """

    settings = get_settings()
    docs_enabled = settings.environment != "production"

    # Mount FastMCP server first (before creating FastAPI app)
    # This sets up the _mcp_app global needed by get_mcp_lifespan()
    # We'll use a temporary app just to mount, then transfer
    # temp_app = FastAPI()
    # _mount_fastmcp_server(temp_app)

    # Now create the lifespan that incorporates MCP lifespan
    lifespan = create_lifespan()

    # Create FastAPI app with combined lifespan
    app = FastAPI(
        title="Agent Socket.IO API",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allows all origins
        allow_credentials=True,
        allow_methods=["*"],  # Allows all methods
        allow_headers=["*"],  # Allows all headers
    )

    # Add session middleware for OAuth state and PKCE storage
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.oauth.session_secret_key,
        same_site="lax",
        https_only=False,
    )
    # Add request tracing middleware (must be before exception middleware)
    app.middleware("http")(request_tracing_middleware)
    app.middleware("http")(exception_logging_middleware)
    app.add_middleware(GZipMiddleware)

    @app.middleware("http")
    async def normalize_mcp_path(request: Request, call_next):
        """
        Normalize /mcp to /mcp/ internally to avoid 307 redirects that can drop auth headers.
        This rewrites the path in-place so clients can POST to /mcp without losing Authorization.
        """
        if request.scope.get("path") == "/mcp":
            request.scope["path"] = "/mcp/"
        return await call_next(request)

    # Register exception handlers
    app.exception_handler(IIAgentError)(ii_agent_error_handler)
    # Store global args in app state for access in endpoints
    app.state.workspace = settings.workspace_path

    # Include API routers (organized by domain)
    app.include_router(auth_router)  # /auth/*
    app.include_router(users_router)  # /auth/me/* (user profile endpoints)
    app.include_router(sessions_router)  # /sessions/*
    app.include_router(credits_router)  # /credits/*
    app.include_router(llm_settings_router)  # /user-settings/llm/*
    app.include_router(mcp_settings_router)  # /user-settings/mcp/*
    app.include_router(skills_settings_router)  # /user-settings/skills/*
    app.include_router(files_router)  # /files/*
    app.include_router(slides_router)  # /slides/*
    app.include_router(slide_templates_router)  # /slide-templates/*
    app.include_router(wishlist_router)  # /wishlist/*
    # app.include_router(enhance_prompt_router)  # /enhance-prompt/*
    app.include_router(billing_router)  # /billing/*
    app.include_router(chat_router)  # /chat/*
    app.include_router(connectors_router)  # /connectors/*
    app.include_router(v1_router)  # /v1/test/agent/*
    app.include_router(project_router)  # /project/*
    app.include_router(subdomains_router)  # /subdomains/*
    app.include_router(media_templates_router)  # /media-templates/*
    app.include_router(media_tools_router)  # /media-tools/*
    app.include_router(media_router)  # /media/*
    app.include_router(storybook_router)  # /storybooks/*
    app.include_router(health_router)
    # app.include_router(mcp_wellknown_router)  # /.well-known/* - OAuth discovery at root

    # Mount FastMCP server (already initialized via temp_app above)
    # _mount_fastmcp_server(app)  # /mcp/* - FastMCP server for ChatGPT
    # _mount_a2a_server(app)

    # Create Socket.IO server with increased timeout settings
    global sio
    sio = socketio.AsyncServer(
        async_mode="asgi",
        cors_allowed_origins="*",
        ping_timeout=300,  # 120 seconds before considering connection dead (default is 20s)
        ping_interval=30,  # Send ping every 30 seconds (default is 25s)
        max_http_buffer_size=10 * 1024 * 1024,  # 10MB max message size
        client_manager=session_manager,
    )

    # Setup Socket.IO manager and store in app state for async initialization in lifespan
    sio_manager = SocketIOManager(sio)
    app.state.sio_manager = sio_manager

    # Create Socket.IO ASGI app that wraps FastAPI
    socket_app = socketio.ASGIApp(sio, app)

    return socket_app


def _mount_fastmcp_server(app: FastAPI, mount_path: str = "/mcp") -> None:
    """Mount the FastMCP server for ChatGPT integration.

    Note: We use a sync approach to create the MCP server since
    FastAPI's app creation happens before the event loop starts.
    """
    try:
        from ii_agent.integrations.mcp_sse.fastmcp_server import mount_to_fastapi

        mount_to_fastapi(app, mount_path)

    except Exception as exc:
        logger.warning("Failed to mount FastMCP server: %s", exc, exc_info=True)


def _mount_a2a_server(app: FastAPI, mount_path: str = "/a2a") -> None:
    """Mount the embedded A2A server as a sub-application."""

    try:
        from ii_agent.integrations.a2a.config import A2AConfig
        from ii_agent.integrations.a2a.__main__ import (
            create_a2a_asgi_app,
            resolve_agent_card_base_url,
        )

        a2a_config = A2AConfig()
        a2a_asgi = create_a2a_asgi_app(a2a_config)
        app.mount(mount_path, a2a_asgi)
        logger.info("Mounted embedded A2A server at %s", mount_path)
        card_base = resolve_agent_card_base_url(a2a_config)
        logger.info(
            "Embedded A2A Agent Card available at %s/.well-known/agent-card.json",
            card_base.rstrip("/"),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to mount embedded A2A server: %s", exc, exc_info=True)
