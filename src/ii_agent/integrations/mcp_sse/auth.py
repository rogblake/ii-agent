"""Authentication for MCP SSE server using OAuth Client Credentials."""

import base64
import logging
import secrets
import time
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, Request

from ii_agent.core.config.settings import get_settings

logger = logging.getLogger(__name__)

# In-memory storage for issued access tokens (use Redis in production)
# Maps token -> {client_id, issued_at, expires_in}
_issued_tokens: Dict[str, Dict[str, Any]] = {}


def store_issued_token(
    token: str,
    client_id: str,
    expires_in: int = 3600,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    resource: Optional[str] = None,
) -> None:
    """Store an issued access token with optional user info and resource (audience)."""
    _issued_tokens[token] = {
        "client_id": client_id,
        "issued_at": time.time(),
        "expires_in": expires_in,
        "user_id": user_id,
        "user_email": user_email,
        "resource": resource,  # OAuth 2.1 resource/audience claim
    }


def validate_bearer_token(token: str) -> Optional[str]:
    """
    Validate a bearer token and return the client_id if valid.

    Returns:
        client_id if token is valid, None otherwise
    """
    token_data = _issued_tokens.get(token)
    if not token_data:
        return None

    # Check if token expired
    if time.time() - token_data["issued_at"] > token_data["expires_in"]:
        del _issued_tokens[token]
        return None

    return token_data["client_id"]


def extract_bearer_token(request: Request) -> Optional[str]:
    """Extract Bearer token from Authorization header."""
    auth_header = request.headers.get("Authorization")
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
    return None


def extract_client_credentials(request: Request) -> Optional[Tuple[str, str]]:
    """
    Extract OAuth client credentials from the request.

    Supports two methods:
    1. Basic Auth: Authorization: Basic base64(client_id:client_secret)
    2. Headers: X-Client-ID and X-Client-Secret headers

    Args:
        request: FastAPI request

    Returns:
        Tuple of (client_id, client_secret) if present, None otherwise
    """
    # Method 1: Basic Auth header
    auth_header = request.headers.get("Authorization")
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "basic":
            try:
                decoded = base64.b64decode(parts[1]).decode("utf-8")
                if ":" in decoded:
                    client_id, client_secret = decoded.split(":", 1)
                    return (client_id, client_secret)
            except Exception:
                pass

    # Method 2: Custom headers
    client_id = request.headers.get("X-Client-ID")
    client_secret = request.headers.get("X-Client-Secret")
    if client_id and client_secret:
        return (client_id, client_secret)

    return None


def validate_client_credentials(client_id: str, client_secret: str) -> bool:
    """
    Validate OAuth client credentials against configured values.

    Args:
        client_id: OAuth Client ID
        client_secret: OAuth Client Secret

    Returns:
        True if credentials are valid, False otherwise
    """
    settings = get_settings()
    configured_client_id = settings.mcp.oauth_client_id
    configured_client_secret = settings.mcp.oauth_client_secret

    # If no credentials configured, reject all
    if not configured_client_id or not configured_client_secret:
        logger.warning("MCP OAuth credentials not configured")
        return False

    # Use constant-time comparison to prevent timing attacks
    id_match = secrets.compare_digest(client_id, configured_client_id)
    secret_match = secrets.compare_digest(client_secret, configured_client_secret)

    return id_match and secret_match


def is_auth_configured() -> bool:
    """Check if OAuth authentication is configured."""
    settings = get_settings()
    return bool(settings.mcp.oauth_client_id and settings.mcp.oauth_client_secret)


def get_www_authenticate_header(request: Request) -> str:
    """Build WWW-Authenticate header value with resource metadata URL."""
    base_url = str(request.base_url).rstrip("/")
    resource_metadata_url = f"{base_url}/mcp/.well-known/oauth-protected-resource"
    return f'Bearer resource_metadata="{resource_metadata_url}"'


async def authenticate_request(request: Request) -> Tuple[str, str]:
    """
    Authenticate an MCP request using OAuth.

    Supports:
    1. Bearer token (from OAuth token endpoint)
    2. Basic Auth (client_id:client_secret)
    3. X-Client-ID/X-Client-Secret headers

    If no credentials are configured, allows anonymous access.

    Args:
        request: FastAPI request

    Returns:
        Tuple of (user_id, client_id)

    Raises:
        HTTPException: If authentication fails (when auth is configured)
    """
    # If auth is not configured, allow anonymous access
    if not is_auth_configured():
        logger.debug("MCP OAuth not configured - allowing anonymous access")
        return ("anonymous", "anonymous")

    www_auth_header = get_www_authenticate_header(request)

    # Method 1: Check for Bearer token (from OAuth flow)
    bearer_token = extract_bearer_token(request)
    if bearer_token:
        client_id = validate_bearer_token(bearer_token)
        if client_id:
            logger.debug(f"MCP request authenticated via Bearer token for client {client_id}")
            return ("mcp_client", client_id)
        else:
            logger.warning("MCP request with invalid or expired Bearer token")
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired access token",
                headers={"WWW-Authenticate": www_auth_header},
            )

    # Method 2: Check for client credentials (Basic Auth or custom headers)
    credentials = extract_client_credentials(request)

    if not credentials:
        logger.warning("MCP request missing client credentials")
        raise HTTPException(
            status_code=401,
            detail="Missing authentication. Use 'Authorization: Bearer <token>' or 'Authorization: Basic base64(client_id:client_secret)'",
            headers={"WWW-Authenticate": www_auth_header},
        )

    client_id, client_secret = credentials

    if not validate_client_credentials(client_id, client_secret):
        logger.warning(f"MCP request with invalid client credentials: {client_id}")
        raise HTTPException(
            status_code=401,
            detail="Invalid client credentials",
            headers={"WWW-Authenticate": www_auth_header},
        )

    logger.debug(f"MCP request authenticated for client {client_id}")
    return ("mcp_client", client_id)

