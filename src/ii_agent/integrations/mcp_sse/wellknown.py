"""Root-level OAuth discovery endpoints for MCP server."""

from typing import Dict, Any
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ii_agent.core.config.settings import Settings
from ii_agent.core.dependencies import SettingsDep

wellknown_router = APIRouter(tags=["oauth-discovery"])


def _get_mcp_base_url(request: Request, settings: Settings) -> str:
    """Get MCP base URL from request or MCP_API_URL."""
    public_url = settings.mcp_api_url
    if public_url:
        public_url = public_url.rstrip("/")
        return public_url if public_url.endswith("/mcp") else f"{public_url}/mcp"

    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_proto or forwarded_host:
        proto = forwarded_proto.split(",")[0].strip() if forwarded_proto else request.url.scheme
        host = forwarded_host.split(",")[0].strip() if forwarded_host else request.url.netloc
        return f"{proto}://{host}/mcp".rstrip("/")

    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/mcp"


def _get_oauth_authorization_server_metadata(request: Request, settings: Settings) -> dict:
    """Build OAuth 2.0 Authorization Server Metadata (RFC 8414)."""
    mcp_base = _get_mcp_base_url(request, settings)

    return {
        "issuer": mcp_base,
        "authorization_endpoint": f"{mcp_base}/oauth/authorize",
        "token_endpoint": f"{mcp_base}/oauth/token",
        "registration_endpoint": f"{mcp_base}/oauth/register",
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
            "none"
        ],
        "grant_types_supported": [
            "authorization_code",
            "client_credentials"
        ],
        "response_types_supported": ["code"],
        "scopes_supported": ["mcp:tools"],
        "code_challenge_methods_supported": ["S256"],
        "client_id_metadata_document_supported": True,
        "service_documentation": f"{mcp_base}/docs",
    }


def _get_openid_config(request: Request, settings: Settings) -> dict:
    """Build OpenID Connect discovery document."""
    mcp_base = _get_mcp_base_url(request, settings)

    return {
        "issuer": mcp_base,
        "authorization_endpoint": f"{mcp_base}/oauth/authorize",
        "token_endpoint": f"{mcp_base}/oauth/token",
        "registration_endpoint": f"{mcp_base}/oauth/register",
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
            "none"
        ],
        "grant_types_supported": [
            "authorization_code",
            "client_credentials"
        ],
        "response_types_supported": ["code", "token"],
        "scopes_supported": ["mcp:tools", "openid"],
        "code_challenge_methods_supported": ["S256"],
        "service_documentation": f"{mcp_base}/docs",
    }


def _get_protected_resource_metadata(request: Request, settings: Settings) -> dict:
    """Build OAuth Protected Resource Metadata (RFC 9728)."""
    mcp_base = _get_mcp_base_url(request, settings)

    return {
        "resource": mcp_base,
        "authorization_servers": [mcp_base],
        "scopes_supported": ["mcp:tools"],
        "bearer_methods_supported": ["header"],
    }


# ============================================================================
# Root-level .well-known endpoints (for ChatGPT that might check root)
# ============================================================================


@wellknown_router.get("/.well-known/oauth-protected-resource")
async def root_oauth_protected_resource(request: Request, settings: SettingsDep):
    """Root-level OAuth Protected Resource Metadata."""
    return JSONResponse(content=_get_protected_resource_metadata(request, settings))


@wellknown_router.get("/.well-known/oauth-protected-resource/mcp")
async def root_oauth_protected_resource_mcp(request: Request, settings: SettingsDep):
    """OAuth Protected Resource Metadata for MCP path."""
    return JSONResponse(content=_get_protected_resource_metadata(request, settings))


@wellknown_router.get("/.well-known/oauth-authorization-server")
async def root_oauth_authorization_server(request: Request, settings: SettingsDep):
    """Root-level OAuth 2.0 Authorization Server Metadata."""
    return JSONResponse(content=_get_oauth_authorization_server_metadata(request, settings))


@wellknown_router.get("/.well-known/oauth-authorization-server/mcp")
async def root_oauth_authorization_server_mcp(request: Request, settings: SettingsDep):
    """
    OAuth 2.0 Authorization Server Metadata for MCP path.

    ChatGPT requests this specific path: /.well-known/oauth-authorization-server/mcp
    """
    return JSONResponse(content=_get_oauth_authorization_server_metadata(request, settings))


@wellknown_router.get("/.well-known/openid-configuration")
async def root_openid_configuration(request: Request, settings: SettingsDep):
    """Root-level OpenID Connect Discovery endpoint."""
    return JSONResponse(content=_get_openid_config(request, settings))


@wellknown_router.get("/.well-known/openid-configuration/mcp")
async def root_openid_configuration_mcp(request: Request, settings: SettingsDep):
    """Root-level OpenID Connect Discovery for MCP path."""
    return JSONResponse(content=_get_openid_config(request, settings))
