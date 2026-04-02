"""FastAPI integration for MCP SSE server."""

import logging
from typing import Optional

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount, Route

from .middleware import AcceptHeaderMiddleware
from .oauth import (
    health_handler,
    oauth_authorization_server_handler,
    oauth_authorize_handler,
    oauth_consent_handler,
    oauth_ii_callback_handler,
    oauth_protected_resource_handler,
    oauth_register_handler,
    oauth_token_handler,
)
from .server import create_mcp_server_sync

logger = logging.getLogger(__name__)

# Global state for mounted app
_mcp_app = None
_fastmcp_http_app = None  # Store FastMCP http_app for lifespan access


def mount_to_fastapi(app, mount_path: str = "/mcp"):
    """Mount the FastMCP server to a FastAPI app.

    This uses FastMCP's http_app() as shown in OpenAI examples.
    The MCP JSON-RPC endpoint will be at /mcp/ (POST).

    IMPORTANT: After calling this function, you must incorporate the returned
    MCP lifespan into your FastAPI app's lifespan. Use get_mcp_lifespan() to
    get the lifespan function, then call it within your app's lifespan context.
    """
    global _mcp_app, _fastmcp_http_app

    mcp_server = create_mcp_server_sync()
    if mcp_server is None:
        logger.warning("Failed to create MCP server, skipping mount")
        return

    # Reuse existing http_app if already created
    if _mcp_app is not None:
        app.mount(mount_path, _mcp_app)
        logger.info(f"Reusing existing FastMCP server at {mount_path}")
        return mcp_server

    # Use http_app() with path="/" so when mounted at /mcp, endpoint is /mcp/
    # Default path is "/mcp/" which would make it /mcp/mcp/ when mounted at /mcp
    # Note: We keep json_response=False (default) because MCP protocol requires
    # SSE streaming for the main endpoint. The text/event-stream content-type is correct.
    fastmcp_http_app = mcp_server.http_app(path="/")

    # Store FastMCP http_app for lifespan access
    _fastmcp_http_app = fastmcp_http_app

    # Create OAuth and well-known routes that return JSON (not SSE)
    # Include both with and without trailing slash to ensure proper matching
    oauth_routes = [
        Route("/health", health_handler, methods=["GET"]),
        Route("/health/", health_handler, methods=["GET"]),
        Route("/.well-known/oauth-protected-resource", oauth_protected_resource_handler, methods=["GET"]),
        Route("/.well-known/oauth-protected-resource/", oauth_protected_resource_handler, methods=["GET"]),
        Route("/.well-known/oauth-authorization-server", oauth_authorization_server_handler, methods=["GET"]),
        Route("/.well-known/oauth-authorization-server/", oauth_authorization_server_handler, methods=["GET"]),
        Route("/.well-known/openid-configuration", oauth_authorization_server_handler, methods=["GET"]),
        Route("/.well-known/openid-configuration/", oauth_authorization_server_handler, methods=["GET"]),
        Route("/oauth/register", oauth_register_handler, methods=["POST"]),
        Route("/oauth/register/", oauth_register_handler, methods=["POST"]),
        Route("/oauth/authorize", oauth_authorize_handler, methods=["GET"]),
        Route("/oauth/authorize/", oauth_authorize_handler, methods=["GET"]),
        Route("/oauth/ii-callback", oauth_ii_callback_handler, methods=["GET"]),  # II OAuth callback
        Route("/oauth/ii-callback/", oauth_ii_callback_handler, methods=["GET"]),
        Route("/oauth/consent", oauth_consent_handler, methods=["POST"]),  # Consent form submission
        Route("/oauth/consent/", oauth_consent_handler, methods=["POST"]),
        Route("/oauth/token", oauth_token_handler, methods=["POST"]),
        Route("/oauth/token/", oauth_token_handler, methods=["POST"]),
        # ChatGPT may request these non-standard paths for discovery
        Route("/oauth/token/.well-known/openid-configuration", oauth_authorization_server_handler, methods=["GET"]),
        Route("/oauth/token/.well-known/openid-configuration/", oauth_authorization_server_handler, methods=["GET"]),
    ]

    # Create a wrapper Starlette app that handles OAuth routes first,
    # then falls back to FastMCP for MCP protocol requests (POST /)
    # This ensures OAuth endpoints return JSON, not SSE
    wrapper_app = Starlette(
        routes=oauth_routes
        + [
            # Mount FastMCP at root - it will handle POST / for MCP protocol
            Mount("/", app=fastmcp_http_app),
        ],
    )

    # Store the wrapper app for mounting
    _mcp_app = wrapper_app

    # Add Accept header middleware to handle clients that don't send text/event-stream
    try:
        wrapper_app.add_middleware(AcceptHeaderMiddleware)
    except Exception as e:
        logger.warning(f"Failed to add AcceptHeaderMiddleware: {e}")

    # Add CORS middleware
    try:
        wrapper_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=False,
        )
    except Exception:
        pass

    # Mount at /mcp
    app.mount(mount_path, wrapper_app)

    logger.info(f"Mounted FastMCP server at {mount_path}")
    return mcp_server


def get_mcp_lifespan():
    """Get the FastMCP lifespan function.

    This must be called within your FastAPI app's lifespan context to
    properly initialize the MCP server's task group.

    Usage in app.py:
        from ii_agent.integrations.mcp_sse import get_mcp_lifespan

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            mcp_lifespan = get_mcp_lifespan()
            async with mcp_lifespan(app):
                # Your other startup code
                yield
                # Your shutdown code
    """
    global _fastmcp_http_app
    if _fastmcp_http_app is None:
        return None
    return _fastmcp_http_app.lifespan
