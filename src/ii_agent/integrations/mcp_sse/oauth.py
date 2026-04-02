"""OAuth 2.0 handlers and PKCE support for MCP SSE server.

This module implements OAuth 2.1 with PKCE for MCP authorization as required by
the OpenAI Apps SDK / ChatGPT integration. When ChatGPT connects to the MCP server,
users are redirected to ii.inc to authenticate before granting access.

Flow:
1. ChatGPT calls /oauth/authorize with PKCE parameters
2. User is shown a login page and clicks "Login with II"
3. User authenticates at ii.inc and is redirected back
4. Authorization code is issued and sent to ChatGPT's redirect URI
5. ChatGPT exchanges code for access token via /oauth/token
"""

import asyncio
import base64
import hashlib
import logging
import secrets
import time as time_module
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
from starlette.responses import JSONResponse, RedirectResponse

from ii_agent.core.config.settings import get_settings
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.integrations.connectors.service import ConnectorService
from .auth import (
    is_auth_configured,
    store_issued_token,
    validate_client_credentials,
)

logger = logging.getLogger(__name__)

# OAuth token expiry in seconds (default: 30 days)
MCP_OAUTH_TOKEN_EXPIRY = get_settings().mcp.oauth_token_expiry

# In-memory storage for OAuth (use Redis in production)
# Note: _issued_tokens is shared with auth.py via store_issued_token()
_authorization_codes: Dict[str, Dict[str, Any]] = {}
_registered_clients: Dict[str, Dict[str, Any]] = {}

# Pending OAuth authorizations (waiting for user to complete ii.inc login)
# Maps ii_state -> original OAuth request params
_pending_authorizations: Dict[str, Dict[str, Any]] = {}

# Pending consents (waiting for user to approve/deny after ii.inc login)
# Maps consent_id -> authorization data with user info
_pending_consents: Dict[str, Dict[str, Any]] = {}


def _get_mcp_base_url(request) -> str:
    """Get MCP base URL from request or config.
    
    Uses MCP_API_URL env var if set, otherwise falls back to request.base_url.
    This is critical for OAuth - ChatGPT needs a publicly accessible URL.
    """
    public_url = get_settings().mcp_api_url
    if public_url:
        # Allow MCP_API_URL to include or omit the /mcp suffix
        public_url = public_url.rstrip("/")
        return public_url if public_url.endswith("/mcp") else f"{public_url}/mcp"

    # Respect reverse proxy headers to preserve the public https scheme/host
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_proto or forwarded_host:
        proto = forwarded_proto.split(",")[0].strip() if forwarded_proto else request.url.scheme
        host = forwarded_host.split(",")[0].strip() if forwarded_host else request.url.netloc
        return f"{proto}://{host}/mcp".rstrip("/")

    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/mcp"


def _get_oauth_metadata(request) -> dict:
    """Build OAuth 2.0 Authorization Server Metadata."""
    mcp_base = _get_mcp_base_url(request)
    return {
        "issuer": mcp_base,
        "authorization_endpoint": f"{mcp_base}/oauth/authorize",
        "token_endpoint": f"{mcp_base}/oauth/token",
        "registration_endpoint": f"{mcp_base}/oauth/register",
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post", "none"],
        "grant_types_supported": ["authorization_code", "client_credentials"],
        "response_types_supported": ["code"],
        "scopes_supported": ["mcp:tools"],
        "code_challenge_methods_supported": ["S256"],
    }


def _get_protected_resource_metadata(request) -> dict:
    """Build OAuth Protected Resource Metadata."""
    mcp_base = _get_mcp_base_url(request)
    return {
        "resource": mcp_base,
        "authorization_servers": [mcp_base],
        "scopes_supported": ["mcp:tools"],
        "bearer_methods_supported": ["header"],
    }


def _verify_pkce(code_verifier: str, code_challenge: str, method: str = "S256") -> bool:
    """Verify PKCE code_verifier against stored code_challenge."""
    if method == "S256":
        # SHA256 hash of verifier, base64url encoded
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        computed_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return secrets.compare_digest(computed_challenge, code_challenge)
    elif method == "plain":
        return secrets.compare_digest(code_verifier, code_challenge)
    return False


def _make_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge pair."""
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


# ========================================================================
# OAuth and Health Route Handlers (standalone functions for Starlette)
# ========================================================================


async def health_handler(request):
    """Health check endpoint."""
    return JSONResponse({"status": "ok"}, status_code=200)


async def oauth_protected_resource_handler(request):
    """OAuth 2.0 Protected Resource Metadata."""
    return JSONResponse(_get_protected_resource_metadata(request))


async def oauth_authorization_server_handler(request):
    """OAuth 2.0 Authorization Server Metadata."""
    return JSONResponse(_get_oauth_metadata(request))


async def oauth_register_handler(request):
    """OAuth 2.0 Dynamic Client Registration."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    client_id = f"dyn_{secrets.token_urlsafe(16)}"
    client_secret = secrets.token_urlsafe(32)

    _registered_clients[client_id] = {
        "client_secret": client_secret,
        "redirect_uris": data.get("redirect_uris", []),
        "client_name": data.get("client_name", "Unknown"),
    }

    logger.info(f"Registered OAuth client: {client_id}")

    return JSONResponse(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "client_name": data.get("client_name", "Unknown"),
            "redirect_uris": data.get("redirect_uris", []),
        },
        status_code=201,
    )


async def oauth_authorize_handler(request):
    """OAuth 2.0 Authorization endpoint with PKCE support.

    This endpoint redirects users to ii.inc to authenticate and consent.
    ii.inc handles showing login (if needed) or consent page (if already logged in).
    After user consents at ii.inc, they are redirected back to /oauth/ii-callback.
    """
    response_type = request.query_params.get("response_type")
    client_id = request.query_params.get("client_id")
    redirect_uri = request.query_params.get("redirect_uri")
    state = request.query_params.get("state")
    scope = request.query_params.get("scope", "mcp:tools")
    resource = request.query_params.get("resource")  # ChatGPT sends this
    # PKCE parameters
    code_challenge = request.query_params.get("code_challenge")
    code_challenge_method = request.query_params.get("code_challenge_method", "S256")

    if not response_type or not client_id or not redirect_uri:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    if response_type != "code":
        return JSONResponse({"error": "unsupported_response_type"}, status_code=400)

    settings = get_settings()

    # Check if MCP external OAuth provider is configured
    if not settings.mcp.ii_client_id:
        # No external OAuth provider - redirect to frontend for user login/consent
        # Generate a consent ID to track this authorization request
        consent_id = secrets.token_urlsafe(32)
        mcp_base = _get_mcp_base_url(request)

        # Store pending authorization for when user completes consent
        _pending_consents[consent_id] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": scope,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "resource": resource,  # OAuth 2.1 resource parameter
            "created_at": time_module.time(),
            "expires_in": 600,  # 10 minutes to complete consent
        }

        # Redirect to frontend consent page (at /oauth/consent)
        frontend_url = settings.ii_frontend_url.rstrip("/")
        consent_params = {
            "consent_id": consent_id,
            "client_id": client_id,
            "scope": scope,
        }
        consent_url = f"{frontend_url}/oauth/consent?{urlencode(consent_params)}"
        logger.info(f"MCP OAuth: Redirecting to frontend for consent: {consent_url}")
        return RedirectResponse(url=consent_url, status_code=302)

    # Generate state for external OAuth flow
    ii_state = secrets.token_urlsafe(32)
    ii_code_verifier, ii_code_challenge = _make_pkce_pair()

    # Store the original OAuth request params
    mcp_base = _get_mcp_base_url(request)
    _pending_authorizations[ii_state] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": scope,
        "resource": resource,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "ii_code_verifier": ii_code_verifier,
        "created_at": time_module.time(),
        "expires_in": 600,  # 10 minutes to complete login
    }

    # Build external OAuth authorization URL and redirect
    ii_callback_url = f"{mcp_base}/oauth/ii-callback"
    ii_params = {
        "client_id": settings.mcp.ii_client_id,
        "response_type": "code",
        "redirect_uri": ii_callback_url,
        "scope": settings.mcp.ii_scope,
        "state": ii_state,
        "code_challenge": ii_code_challenge,
        "code_challenge_method": "S256",
    }
    ii_auth_url = f"{settings.mcp_ii_auth_url}?{urlencode(ii_params)}"
    logger.info(f"OAuth: using mcp_ii_client_id={settings.mcp.ii_client_id}, ii_callback_url={ii_callback_url}")

    logger.info(f"OAuth authorize: redirecting to external OAuth for client {client_id}")
    return RedirectResponse(url=ii_auth_url, status_code=302)


def _complete_authorization(
    client_id: str,
    redirect_uri: str,
    state: Optional[str],
    scope: str,
    code_challenge: Optional[str],
    code_challenge_method: str,
    user_id: str,
    user_email: Optional[str],
    resource: Optional[str] = None,
    return_json: bool = False,
):
    """Complete the OAuth authorization by issuing an authorization code.
    
    Args:
        resource: OAuth 2.1 resource parameter (audience) - echoed in token response per MCP spec.
        return_json: If True, return JSONResponse with redirect_url instead of RedirectResponse.
                    This is needed for frontend fetch() calls that can't follow cross-origin redirects.
    """
    auth_code = secrets.token_urlsafe(32)
    _authorization_codes[auth_code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "created_at": time_module.time(),
        "expires_in": 600,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "user_id": user_id,
        "user_email": user_email,
        "resource": resource,
    }

    params = {"code": auth_code}
    if state:
        params["state"] = state

    redirect_url = f"{redirect_uri}?{urlencode(params)}"
    logger.info(f"OAuth authorize: redirecting with code for user {user_id}")
    
    if return_json:
        return JSONResponse({"redirect_url": redirect_url})
    return RedirectResponse(url=redirect_url, status_code=302)


async def oauth_ii_callback_handler(request):
    """Handle callback from II OAuth after user authentication.

    This completes the MCP OAuth flow by:
    1. Exchanging the II auth code for tokens
    2. Extracting user info from the ID token
    3. Issuing an MCP authorization code back to ChatGPT
    """
    code = request.query_params.get("code")
    ii_state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        logger.error(f"II OAuth error: {error}")
        return JSONResponse(
            {"error": "access_denied", "error_description": f"II OAuth error: {error}"},
            status_code=400
        )

    if not code or not ii_state:
        return JSONResponse(
            {"error": "invalid_request", "error_description": "Missing code or state"},
            status_code=400
        )

    # Retrieve pending authorization
    pending = _pending_authorizations.pop(ii_state, None)
    if not pending:
        logger.warning(f"Unknown or expired II OAuth state: {ii_state[:10]}...")
        return JSONResponse(
            {"error": "invalid_request", "error_description": "Unknown or expired authorization request"},
            status_code=400
        )

    # Check if pending authorization has expired
    if time_module.time() - pending["created_at"] > pending["expires_in"]:
        logger.warning("Pending authorization expired")
        return JSONResponse(
            {"error": "invalid_request", "error_description": "Authorization request expired"},
            status_code=400
        )

    # Exchange II auth code for tokens
    # Use the same redirect URI that was used in the authorization request
    # Use MCP-specific OAuth config (separate from main ii.inc OAuth)
    mcp_base = _get_mcp_base_url(request)
    ii_callback_url = f"{mcp_base}/oauth/ii-callback"

    settings = get_settings()

    try:
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": ii_callback_url,
            "client_id": settings.mcp.ii_client_id,  # MCP-specific client ID
            "code_verifier": pending["ii_code_verifier"],
        }

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                settings.mcp_ii_token_url,  # MCP-specific token URL
                data=token_data,
                headers={"content-type": "application/x-www-form-urlencoded"},
            )

        if response.status_code != 200:
            logger.error(f"II token exchange failed: {response.status_code} {response.text}")
            return JSONResponse(
                {"error": "server_error", "error_description": "Failed to exchange authorization code"},
                status_code=500
            )

        token_response = response.json()
        id_token = token_response.get("id_token")

        # Extract user info from ID token (basic JWT parsing)
        user_id = "ii_user"
        user_email = None
        user_name = "II User"

        if id_token:
            try:
                # Parse JWT payload (middle part)
                parts = id_token.split(".")
                if len(parts) >= 2:
                    # Add padding if needed
                    payload_b64 = parts[1]
                    padding = 4 - len(payload_b64) % 4
                    if padding != 4:
                        payload_b64 += "=" * padding

                    import json
                    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                    user_id = payload.get("sub", "ii_user")
                    user_email = payload.get("email")
                    user_name = payload.get("name") or payload.get("preferred_username") or user_id
                    logger.info(f"II OAuth: authenticated user {user_id} ({user_email})")
            except Exception as e:
                logger.warning(f"Failed to parse ID token: {e}")

        # Store pending consent and show consent page
        consent_id = secrets.token_urlsafe(32)
        _pending_consents[consent_id] = {
            "client_id": pending["client_id"],
            "redirect_uri": pending["redirect_uri"],
            "state": pending["state"],
            "scope": pending["scope"],
            "code_challenge": pending["code_challenge"],
            "code_challenge_method": pending["code_challenge_method"],
            "resource": pending.get("resource"),  # OAuth 2.1 resource parameter
            "user_id": user_id,
            "user_email": user_email,
            "user_name": user_name,
            "created_at": time_module.time(),
            "expires_in": 600,  # 10 minutes to complete consent
        }

        # Get client name for display
        client_info = _registered_clients.get(pending["client_id"], {})
        client_name = client_info.get("client_name", "ChatGPT")

        logger.info(f"II OAuth: redirecting to frontend consent page for user {user_id}")

        # Redirect to frontend consent page
        # The frontend URL is derived from II_FRONTEND_URL env var or defaults to same origin
        frontend_url = settings.ii_frontend_url
        consent_params = urlencode({
            "consent_id": consent_id,
            "client_name": client_name,
            "scope": pending["scope"],
        })
        consent_url = f"{frontend_url}/oauth/consent?{consent_params}"
        return RedirectResponse(url=consent_url, status_code=302)

    except Exception as e:
        logger.error(f"II OAuth callback error: {e}", exc_info=True)
        return JSONResponse(
            {"error": "server_error", "error_description": "Authentication failed"},
            status_code=500
        )


async def oauth_consent_handler(request):
    """Handle user consent decision (Allow/Deny).

    This is called when user clicks Allow or Deny on the consent page.
    Accepts both form data (POST) and JSON body.

    Required fields:
    - consent_id: The consent ID from the authorization request
    - action: "allow" or "deny"
    - user_id: The authenticated user's ID (required for "allow")
    - user_email: The authenticated user's email (optional)
    """
    try:
        # Try to get data from JSON body first, then form data
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            data = await request.json()
            consent_id = data.get("consent_id")
            action = data.get("action")
            user_id = data.get("user_id")
            user_email = data.get("user_email")
        else:
            form_data = await request.form()
            consent_id = form_data.get("consent_id")
            action = form_data.get("action")
            user_id = form_data.get("user_id")
            user_email = form_data.get("user_email")

        if not consent_id or not action:
            return JSONResponse(
                {"error": "invalid_request", "error_description": "Missing consent_id or action"},
                status_code=400
            )

        # Retrieve pending consent
        consent = _pending_consents.pop(consent_id, None)
        if not consent:
            logger.warning(f"Unknown or expired consent: {consent_id[:10]}...")
            return JSONResponse(
                {"error": "invalid_request", "error_description": "Unknown or expired consent request"},
                status_code=400
            )

        # Check if consent has expired
        if time_module.time() - consent["created_at"] > consent["expires_in"]:
            logger.warning("Consent expired")
            return JSONResponse(
                {"error": "invalid_request", "error_description": "Consent request expired"},
                status_code=400
            )

        if action == "deny":
            # User denied - return redirect URL as JSON (frontend will navigate)
            params = {"error": "access_denied", "error_description": "User denied the request"}
            if consent["state"]:
                params["state"] = consent["state"]
            redirect_url = f"{consent['redirect_uri']}?{urlencode(params)}"
            logger.info(f"OAuth consent: user denied access")
            return JSONResponse({"redirect_url": redirect_url})

        elif action == "allow":
            # User allowed - get user info from request or consent data
            final_user_id = user_id or consent.get("user_id")
            final_user_email = user_email or consent.get("user_email")

            if not final_user_id:
                return JSONResponse(
                    {"error": "invalid_request", "error_description": "Missing user_id"},
                    status_code=400
                )

            logger.info(f"OAuth consent: user {final_user_id} allowed access")
            return _complete_authorization(
                client_id=consent["client_id"],
                redirect_uri=consent["redirect_uri"],
                state=consent["state"],
                scope=consent["scope"],
                code_challenge=consent["code_challenge"],
                code_challenge_method=consent["code_challenge_method"],
                user_id=final_user_id,
                user_email=final_user_email,
                resource=consent.get("resource"),  # OAuth 2.1 resource parameter
                return_json=True,  # Return JSON so frontend can navigate (avoids CORS issues)
            )

        else:
            return JSONResponse(
                {"error": "invalid_request", "error_description": "Invalid action"},
                status_code=400
            )

    except Exception as e:
        logger.error(f"Consent handler error: {e}", exc_info=True)
        return JSONResponse(
            {"error": "server_error", "error_description": "Failed to process consent"},
            status_code=500
        )


async def oauth_token_handler(request):
    """OAuth 2.0 Token endpoint with PKCE support.

    Validates client credentials against configured MCP_OAUTH_CLIENT_ID and
    MCP_OAUTH_CLIENT_SECRET environment variables (same as legacy endpoint).
    """
    content_type = request.headers.get("content-type", "")

    grant_type = None
    client_id = None
    client_secret = None
    code = None
    code_verifier = None

    if "application/x-www-form-urlencoded" in content_type:
        form_data = await request.form()
        grant_type = form_data.get("grant_type")
        client_id = form_data.get("client_id")
        client_secret = form_data.get("client_secret")
        code = form_data.get("code")
        code_verifier = form_data.get("code_verifier")
    else:
        try:
            json_data = await request.json()
            grant_type = json_data.get("grant_type")
            client_id = json_data.get("client_id")
            client_secret = json_data.get("client_secret")
            code = json_data.get("code")
            code_verifier = json_data.get("code_verifier")
        except Exception:
            pass

    # Check Basic Auth header
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth_header[6:]).decode()
            if ":" in decoded:
                client_id, client_secret = decoded.split(":", 1)
        except Exception:
            pass

    logger.info(
        f"OAuth token request: grant_type={grant_type}, client_id={client_id}, has_code_verifier={code_verifier is not None}, code={code[:20] if code else None}..."
    )
    logger.info(f"OAuth token request: available codes count={len(_authorization_codes)}")

    if grant_type == "authorization_code":
        if not code:
            return JSONResponse({"error": "invalid_request", "error_description": "Missing code"}, status_code=400)

        code_data = _authorization_codes.get(code)
        if not code_data:
            logger.warning(f"Invalid authorization code: {code[:20]}... (available: {list(_authorization_codes.keys())[:3]})")
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Invalid authorization code"}, status_code=400
            )

        if time_module.time() - code_data["created_at"] > code_data["expires_in"]:
            del _authorization_codes[code]
            return JSONResponse({"error": "invalid_grant", "error_description": "Code expired"}, status_code=400)

        # Verify PKCE if code_challenge was provided during authorization
        stored_challenge = code_data.get("code_challenge")
        if stored_challenge:
            if not code_verifier:
                logger.warning("PKCE required but code_verifier not provided")
                return JSONResponse(
                    {"error": "invalid_request", "error_description": "code_verifier required for PKCE"}, status_code=400
                )

            challenge_method = code_data.get("code_challenge_method", "S256")
            if not _verify_pkce(code_verifier, stored_challenge, challenge_method):
                logger.warning(f"PKCE verification failed for client {client_id}")
                del _authorization_codes[code]
                return JSONResponse(
                    {"error": "invalid_grant", "error_description": "PKCE verification failed"}, status_code=400
                )
            logger.info(f"PKCE verification successful for client {client_id}")

        del _authorization_codes[code]

        access_token = f"mcp_{secrets.token_urlsafe(32)}"
        # Store token with user info from the authorization
        user_id = code_data.get("user_id", "mcp_user")
        user_email = code_data.get("user_email")
        resource = code_data.get("resource")  # OAuth 2.1 resource parameter
        store_issued_token(
            access_token,
            client_id or code_data["client_id"],
            expires_in=MCP_OAUTH_TOKEN_EXPIRY,
            user_id=user_id,
            user_email=user_email,
            resource=resource,
        )

        # Save token to database for persistent lookup (with timeout to avoid blocking)
        try:
            async def _save_token():
                async with get_db_session_local() as db:
                    await ConnectorService(config=get_settings()).save_mcp_token(
                        db,
                        access_token=access_token,
                        user_id=user_id,
                        user_email=user_email,
                        expires_in=MCP_OAUTH_TOKEN_EXPIRY,
                    )
            await asyncio.wait_for(
                _save_token(),
                timeout=5.0,  # 5 second timeout for DB operation
            )
            logger.info(f"MCP token saved to database for user {user_id}")
        except asyncio.TimeoutError:
            logger.warning(f"Database save timed out for user {user_id}, token still valid in memory")
        except Exception as e:
            logger.warning(f"Failed to save MCP token to database: {e}")

        logger.info(f"OAuth token issued for user {user_id} via client {client_id}")

        # Build token response - echo resource parameter per OAuth 2.1 / MCP spec
        token_response = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": MCP_OAUTH_TOKEN_EXPIRY,
            "scope": code_data.get("scope", "mcp:tools"),
        }
        if resource:
            token_response["resource"] = resource

        return JSONResponse(token_response)

    elif grant_type == "client_credentials":
        # Validate client credentials against configured values
        if is_auth_configured():
            if not client_id or not client_secret:
                return JSONResponse(
                    {"error": "invalid_request", "error_description": "client_id and client_secret are required"},
                    status_code=400,
                )

            if not validate_client_credentials(client_id, client_secret):
                logger.warning(f"Invalid client credentials for client_id: {client_id}")
                return JSONResponse(
                    {"error": "invalid_client", "error_description": "Invalid client credentials"}, status_code=401
                )

        access_token = f"mcp_{secrets.token_urlsafe(32)}"
        # Store token in shared storage (accessible by both FastMCP and legacy endpoints)
        store_issued_token(access_token, client_id or "anonymous", expires_in=MCP_OAUTH_TOKEN_EXPIRY)

        return JSONResponse(
            {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": MCP_OAUTH_TOKEN_EXPIRY,
                "scope": "mcp:tools",
            }
        )

    return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
