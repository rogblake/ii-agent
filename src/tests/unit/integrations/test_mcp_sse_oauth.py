"""Unit tests for ii_agent.integrations.mcp_sse.oauth."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from types import SimpleNamespace
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _make_request(
    query_params: Dict[str, str] = None,
    headers: Dict[str, str] = None,
    base_url: str = "http://localhost:8000/",
    url_scheme: str = "http",
    url_netloc: str = "localhost:8000",
):
    """Create a minimal Starlette-like request mock."""
    req = MagicMock()
    req.query_params = query_params or {}
    req.headers = headers or {}
    req.base_url = base_url
    req.url = SimpleNamespace(scheme=url_scheme, netloc=url_netloc)
    return req


def _make_pkce_verifier():
    """Generate a real PKCE verifier + challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


# ---------------------------------------------------------------------------
# _get_mcp_base_url
# ---------------------------------------------------------------------------


class TestGetMcpBaseUrl:
    def test_uses_mcp_api_url_when_set(self):
        from ii_agent.integrations.mcp_sse.oauth import _get_mcp_base_url

        req = _make_request()
        with patch("ii_agent.integrations.mcp_sse.oauth.get_settings") as mock_settings:
            mock_settings.return_value.mcp_api_url = "https://api.example.com"
            result = _get_mcp_base_url(req)
        assert result == "https://api.example.com/mcp"

    def test_mcp_api_url_already_has_mcp_suffix(self):
        from ii_agent.integrations.mcp_sse.oauth import _get_mcp_base_url

        req = _make_request()
        with patch("ii_agent.integrations.mcp_sse.oauth.get_settings") as mock_settings:
            mock_settings.return_value.mcp_api_url = "https://api.example.com/mcp"
            result = _get_mcp_base_url(req)
        assert result == "https://api.example.com/mcp"

    def test_uses_forwarded_headers_when_set(self):
        from ii_agent.integrations.mcp_sse.oauth import _get_mcp_base_url

        req = _make_request(
            headers={
                "x-forwarded-proto": "https",
                "x-forwarded-host": "secure.example.com",
            }
        )
        with patch("ii_agent.integrations.mcp_sse.oauth.get_settings") as mock_settings:
            mock_settings.return_value.mcp_api_url = None
            result = _get_mcp_base_url(req)
        assert result == "https://secure.example.com/mcp"

    def test_falls_back_to_base_url(self):
        from ii_agent.integrations.mcp_sse.oauth import _get_mcp_base_url

        req = _make_request(base_url="http://localhost:8000/")
        with patch("ii_agent.integrations.mcp_sse.oauth.get_settings") as mock_settings:
            mock_settings.return_value.mcp_api_url = None
            result = _get_mcp_base_url(req)
        assert "/mcp" in result

    def test_forwarded_proto_only(self):
        from ii_agent.integrations.mcp_sse.oauth import _get_mcp_base_url

        req = _make_request(headers={"x-forwarded-proto": "https"}, url_netloc="myhost.com")
        with patch("ii_agent.integrations.mcp_sse.oauth.get_settings") as mock_settings:
            mock_settings.return_value.mcp_api_url = None
            result = _get_mcp_base_url(req)
        assert result.startswith("https://")

    def test_forwarded_host_with_comma_separated_uses_first(self):
        from ii_agent.integrations.mcp_sse.oauth import _get_mcp_base_url

        req = _make_request(
            headers={"x-forwarded-host": "primary.com, secondary.com"},
        )
        with patch("ii_agent.integrations.mcp_sse.oauth.get_settings") as mock_settings:
            mock_settings.return_value.mcp_api_url = None
            result = _get_mcp_base_url(req)
        assert "primary.com" in result


# ---------------------------------------------------------------------------
# _get_oauth_metadata
# ---------------------------------------------------------------------------


class TestGetOauthMetadata:
    def test_returns_all_required_fields(self):
        from ii_agent.integrations.mcp_sse.oauth import _get_oauth_metadata

        req = _make_request()
        with patch("ii_agent.integrations.mcp_sse.oauth.get_settings") as ms:
            ms.return_value.mcp_api_url = "https://mcp.example.com"
            result = _get_oauth_metadata(req)

        assert "issuer" in result
        assert "authorization_endpoint" in result
        assert "token_endpoint" in result
        assert "registration_endpoint" in result
        assert "code_challenge_methods_supported" in result
        assert "S256" in result["code_challenge_methods_supported"]

    def test_endpoints_include_mcp_base(self):
        from ii_agent.integrations.mcp_sse.oauth import _get_oauth_metadata

        req = _make_request()
        with patch("ii_agent.integrations.mcp_sse.oauth.get_settings") as ms:
            ms.return_value.mcp_api_url = "https://mcp.example.com"
            result = _get_oauth_metadata(req)

        assert result["authorization_endpoint"].startswith("https://mcp.example.com")
        assert result["token_endpoint"].startswith("https://mcp.example.com")


# ---------------------------------------------------------------------------
# _get_protected_resource_metadata
# ---------------------------------------------------------------------------


class TestGetProtectedResourceMetadata:
    def test_returns_resource_and_auth_servers(self):
        from ii_agent.integrations.mcp_sse.oauth import _get_protected_resource_metadata

        req = _make_request()
        with patch("ii_agent.integrations.mcp_sse.oauth.get_settings") as ms:
            ms.return_value.mcp_api_url = "https://mcp.example.com"
            result = _get_protected_resource_metadata(req)

        assert "resource" in result
        assert "authorization_servers" in result
        assert isinstance(result["authorization_servers"], list)

    def test_bearer_method_supported(self):
        from ii_agent.integrations.mcp_sse.oauth import _get_protected_resource_metadata

        req = _make_request()
        with patch("ii_agent.integrations.mcp_sse.oauth.get_settings") as ms:
            ms.return_value.mcp_api_url = "https://mcp.example.com"
            result = _get_protected_resource_metadata(req)

        assert "header" in result["bearer_methods_supported"]


# ---------------------------------------------------------------------------
# _verify_pkce
# ---------------------------------------------------------------------------


class TestVerifyPKCE:
    def test_valid_s256_challenge(self):
        from ii_agent.integrations.mcp_sse.oauth import _verify_pkce

        verifier, challenge = _make_pkce_verifier()
        assert _verify_pkce(verifier, challenge, "S256") is True

    def test_invalid_s256_challenge(self):
        from ii_agent.integrations.mcp_sse.oauth import _verify_pkce

        _, challenge = _make_pkce_verifier()
        assert _verify_pkce("wrong_verifier", challenge, "S256") is False

    def test_valid_plain_challenge(self):
        from ii_agent.integrations.mcp_sse.oauth import _verify_pkce

        verifier = "my_plain_verifier"
        assert _verify_pkce(verifier, verifier, "plain") is True

    def test_invalid_plain_challenge(self):
        from ii_agent.integrations.mcp_sse.oauth import _verify_pkce

        assert _verify_pkce("verifier", "different", "plain") is False

    def test_unknown_method_returns_false(self):
        from ii_agent.integrations.mcp_sse.oauth import _verify_pkce

        assert _verify_pkce("v", "c", "RS256") is False


# ---------------------------------------------------------------------------
# _make_pkce_pair
# ---------------------------------------------------------------------------


class TestMakePkcePair:
    def test_generates_valid_pair(self):
        from ii_agent.integrations.mcp_sse.oauth import _make_pkce_pair, _verify_pkce

        verifier, challenge = _make_pkce_pair()
        assert _verify_pkce(verifier, challenge, "S256") is True

    def test_verifier_is_string(self):
        from ii_agent.integrations.mcp_sse.oauth import _make_pkce_pair

        verifier, challenge = _make_pkce_pair()
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)

    def test_verifier_is_url_safe(self):
        from ii_agent.integrations.mcp_sse.oauth import _make_pkce_pair

        verifier, _ = _make_pkce_pair()
        for char in verifier:
            assert char in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"


# ---------------------------------------------------------------------------
# health_handler
# ---------------------------------------------------------------------------


class TestHealthHandler:
    @pytest.mark.asyncio
    async def test_returns_200_ok(self):
        from ii_agent.integrations.mcp_sse.oauth import health_handler

        req = _make_request()
        response = await health_handler(req)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_returns_status_ok_body(self):
        from ii_agent.integrations.mcp_sse.oauth import health_handler

        req = _make_request()
        response = await health_handler(req)
        body = json.loads(response.body)
        assert body["status"] == "ok"


# ---------------------------------------------------------------------------
# oauth_protected_resource_handler
# ---------------------------------------------------------------------------


class TestOAuthProtectedResourceHandler:
    @pytest.mark.asyncio
    async def test_returns_metadata(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_protected_resource_handler

        req = _make_request()
        with patch("ii_agent.integrations.mcp_sse.oauth.get_settings") as ms:
            ms.return_value.mcp_api_url = "https://mcp.example.com"
            response = await oauth_protected_resource_handler(req)

        body = json.loads(response.body)
        assert "resource" in body


# ---------------------------------------------------------------------------
# oauth_authorization_server_handler
# ---------------------------------------------------------------------------


class TestOAuthAuthorizationServerHandler:
    @pytest.mark.asyncio
    async def test_returns_metadata(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_authorization_server_handler

        req = _make_request()
        with patch("ii_agent.integrations.mcp_sse.oauth.get_settings") as ms:
            ms.return_value.mcp_api_url = "https://mcp.example.com"
            response = await oauth_authorization_server_handler(req)

        body = json.loads(response.body)
        assert "authorization_endpoint" in body


# ---------------------------------------------------------------------------
# oauth_register_handler
# ---------------------------------------------------------------------------


class TestOAuthRegisterHandler:
    @pytest.mark.asyncio
    async def test_registers_client_and_returns_201(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_register_handler

        req = MagicMock()
        req.json = AsyncMock(
            return_value={
                "client_name": "TestApp",
                "redirect_uris": ["https://app.example.com/callback"],
            }
        )
        response = await oauth_register_handler(req)
        assert response.status_code == 201
        body = json.loads(response.body)
        assert "client_id" in body
        assert "client_secret" in body
        assert body["client_name"] == "TestApp"

    @pytest.mark.asyncio
    async def test_handles_invalid_json(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_register_handler

        req = MagicMock()
        req.json = AsyncMock(side_effect=Exception("bad json"))
        response = await oauth_register_handler(req)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["error"] == "invalid_request"

    @pytest.mark.asyncio
    async def test_client_id_starts_with_dyn(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_register_handler

        req = MagicMock()
        req.json = AsyncMock(return_value={})
        response = await oauth_register_handler(req)
        body = json.loads(response.body)
        assert body["client_id"].startswith("dyn_")


# ---------------------------------------------------------------------------
# oauth_authorize_handler
# ---------------------------------------------------------------------------


class TestOAuthAuthorizeHandler:
    @pytest.mark.asyncio
    async def test_missing_params_returns_400(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_authorize_handler

        req = _make_request(query_params={})
        response = await oauth_authorize_handler(req)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["error"] == "invalid_request"

    @pytest.mark.asyncio
    async def test_wrong_response_type_returns_400(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_authorize_handler

        req = _make_request(
            query_params={
                "response_type": "token",
                "client_id": "client1",
                "redirect_uri": "https://app.com/cb",
            }
        )
        with patch("ii_agent.integrations.mcp_sse.oauth.get_settings") as ms:
            ms.return_value.mcp.ii_client_id = None
            ms.return_value.mcp_api_url = None
            ms.return_value.ii_frontend_url = "https://front.example.com"
            response = await oauth_authorize_handler(req)

        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["error"] == "unsupported_response_type"

    @pytest.mark.asyncio
    async def test_redirects_to_frontend_when_no_external_provider(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_authorize_handler

        verifier, challenge = _make_pkce_verifier()
        req = _make_request(
            query_params={
                "response_type": "code",
                "client_id": "client1",
                "redirect_uri": "https://app.com/cb",
                "state": "state123",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        with patch("ii_agent.integrations.mcp_sse.oauth.get_settings") as ms:
            ms.return_value.mcp.ii_client_id = None
            ms.return_value.mcp_api_url = None
            ms.return_value.ii_frontend_url = "https://front.example.com"
            response = await oauth_authorize_handler(req)

        assert response.status_code == 302
        assert "front.example.com" in response.headers["location"]
        assert "consent_id" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_redirects_to_external_provider_when_configured(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_authorize_handler

        verifier, challenge = _make_pkce_verifier()
        req = _make_request(
            query_params={
                "response_type": "code",
                "client_id": "client1",
                "redirect_uri": "https://app.com/cb",
                "state": "state123",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        with patch("ii_agent.integrations.mcp_sse.oauth.get_settings") as ms:
            ms.return_value.mcp.ii_client_id = "ext_client"
            ms.return_value.mcp.ii_scope = "openid email"
            ms.return_value.mcp_api_url = "https://mcp.example.com"
            ms.return_value.mcp_ii_auth_url = "https://auth.example.com/authorize"
            response = await oauth_authorize_handler(req)

        assert response.status_code == 302
        assert "auth.example.com" in response.headers["location"]


# ---------------------------------------------------------------------------
# _complete_authorization
# ---------------------------------------------------------------------------


class TestCompleteAuthorization:
    def test_returns_redirect_response_by_default(self):
        from ii_agent.integrations.mcp_sse.oauth import _complete_authorization

        response = _complete_authorization(
            client_id="c1",
            redirect_uri="https://app.com/cb",
            state="s1",
            scope="mcp:tools",
            code_challenge=None,
            code_challenge_method="S256",
            user_id="u1",
            user_email="user@example.com",
        )
        assert response.status_code == 302
        assert "code=" in response.headers["location"]

    def test_returns_json_response_when_return_json_true(self):
        from ii_agent.integrations.mcp_sse.oauth import _complete_authorization

        response = _complete_authorization(
            client_id="c1",
            redirect_uri="https://app.com/cb",
            state=None,
            scope="mcp:tools",
            code_challenge=None,
            code_challenge_method="S256",
            user_id="u1",
            user_email=None,
            return_json=True,
        )
        body = json.loads(response.body)
        assert "redirect_url" in body
        assert "code=" in body["redirect_url"]

    def test_state_appended_to_redirect_url(self):
        from ii_agent.integrations.mcp_sse.oauth import _complete_authorization

        response = _complete_authorization(
            client_id="c1",
            redirect_uri="https://app.com/cb",
            state="mystate",
            scope="mcp:tools",
            code_challenge=None,
            code_challenge_method="S256",
            user_id="u1",
            user_email=None,
        )
        assert "state=mystate" in response.headers["location"]

    def test_stores_code_in_authorization_codes(self):
        from ii_agent.integrations.mcp_sse.oauth import (
            _complete_authorization,
            _authorization_codes,
        )

        before = set(_authorization_codes.keys())
        _complete_authorization(
            client_id="c1",
            redirect_uri="https://app.com/cb",
            state=None,
            scope="mcp:tools",
            code_challenge=None,
            code_challenge_method="S256",
            user_id="u1",
            user_email=None,
        )
        after = set(_authorization_codes.keys())
        new_keys = after - before
        assert len(new_keys) == 1


# ---------------------------------------------------------------------------
# oauth_consent_handler
# ---------------------------------------------------------------------------


class TestOAuthConsentHandler:
    @pytest.mark.asyncio
    async def test_missing_consent_id_returns_400(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_consent_handler

        req = MagicMock()
        req.headers = {"content-type": "application/json"}
        req.json = AsyncMock(return_value={"action": "allow"})
        response = await oauth_consent_handler(req)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_unknown_consent_id_returns_400(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_consent_handler

        req = MagicMock()
        req.headers = {"content-type": "application/json"}
        req.json = AsyncMock(
            return_value={"consent_id": "unknown_id", "action": "allow", "user_id": "u1"}
        )
        response = await oauth_consent_handler(req)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_deny_action_returns_redirect_url(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_consent_handler, _pending_consents

        consent_id = "test_consent_deny"
        _pending_consents[consent_id] = {
            "client_id": "c1",
            "redirect_uri": "https://app.com/cb",
            "state": "s1",
            "scope": "mcp:tools",
            "code_challenge": None,
            "code_challenge_method": "S256",
            "user_id": "u1",
            "user_email": None,
            "created_at": time.time(),
            "expires_in": 600,
        }
        req = MagicMock()
        req.headers = {"content-type": "application/json"}
        req.json = AsyncMock(return_value={"consent_id": consent_id, "action": "deny"})
        response = await oauth_consent_handler(req)
        body = json.loads(response.body)
        assert "redirect_url" in body
        assert "access_denied" in body["redirect_url"]

    @pytest.mark.asyncio
    async def test_allow_action_completes_authorization(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_consent_handler, _pending_consents

        consent_id = "test_consent_allow"
        _pending_consents[consent_id] = {
            "client_id": "c1",
            "redirect_uri": "https://app.com/cb",
            "state": "s1",
            "scope": "mcp:tools",
            "code_challenge": None,
            "code_challenge_method": "S256",
            "user_id": "u1",
            "user_email": "u@example.com",
            "created_at": time.time(),
            "expires_in": 600,
        }
        req = MagicMock()
        req.headers = {"content-type": "application/json"}
        req.json = AsyncMock(
            return_value={
                "consent_id": consent_id,
                "action": "allow",
                "user_id": "u1",
            }
        )
        response = await oauth_consent_handler(req)
        body = json.loads(response.body)
        assert "redirect_url" in body
        assert "code=" in body["redirect_url"]

    @pytest.mark.asyncio
    async def test_expired_consent_returns_400(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_consent_handler, _pending_consents

        consent_id = "test_consent_expired"
        _pending_consents[consent_id] = {
            "client_id": "c1",
            "redirect_uri": "https://app.com/cb",
            "state": None,
            "scope": "mcp:tools",
            "code_challenge": None,
            "code_challenge_method": "S256",
            "created_at": time.time() - 700,  # Expired
            "expires_in": 600,
        }
        req = MagicMock()
        req.headers = {"content-type": "application/json"}
        req.json = AsyncMock(
            return_value={"consent_id": consent_id, "action": "allow", "user_id": "u1"}
        )
        response = await oauth_consent_handler(req)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_action_returns_400(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_consent_handler, _pending_consents

        consent_id = "test_bad_action"
        _pending_consents[consent_id] = {
            "client_id": "c1",
            "redirect_uri": "https://app.com/cb",
            "state": None,
            "scope": "mcp:tools",
            "code_challenge": None,
            "code_challenge_method": "S256",
            "created_at": time.time(),
            "expires_in": 600,
        }
        req = MagicMock()
        req.headers = {"content-type": "application/json"}
        req.json = AsyncMock(return_value={"consent_id": consent_id, "action": "maybe"})
        response = await oauth_consent_handler(req)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_form_data_parsing(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_consent_handler, _pending_consents

        consent_id = "test_form_data"
        _pending_consents[consent_id] = {
            "client_id": "c1",
            "redirect_uri": "https://app.com/cb",
            "state": None,
            "scope": "mcp:tools",
            "code_challenge": None,
            "code_challenge_method": "S256",
            "user_id": "u1",
            "user_email": None,
            "created_at": time.time(),
            "expires_in": 600,
        }
        form = {"consent_id": consent_id, "action": "allow", "user_id": "u1"}
        req = MagicMock()
        req.headers = {"content-type": "application/x-www-form-urlencoded"}
        req.form = AsyncMock(return_value=form)
        response = await oauth_consent_handler(req)
        body = json.loads(response.body)
        assert "redirect_url" in body


# ---------------------------------------------------------------------------
# oauth_token_handler
# ---------------------------------------------------------------------------


class TestOAuthTokenHandler:
    @pytest.mark.asyncio
    async def test_unsupported_grant_type_returns_400(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_token_handler

        req = MagicMock()
        req.headers = {"content-type": "application/json"}
        req.json = AsyncMock(return_value={"grant_type": "refresh_token"})
        response = await oauth_token_handler(req)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["error"] == "unsupported_grant_type"

    @pytest.mark.asyncio
    async def test_authorization_code_missing_code_returns_400(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_token_handler

        req = MagicMock()
        req.headers = {"content-type": "application/json"}
        req.json = AsyncMock(return_value={"grant_type": "authorization_code"})
        response = await oauth_token_handler(req)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["error"] == "invalid_request"

    @pytest.mark.asyncio
    async def test_authorization_code_invalid_code_returns_400(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_token_handler

        req = MagicMock()
        req.headers = {"content-type": "application/json"}
        req.json = AsyncMock(return_value={"grant_type": "authorization_code", "code": "bad_code"})
        response = await oauth_token_handler(req)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_authorization_code_expired_code_returns_400(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_token_handler, _authorization_codes

        code = "expired_code_123"
        _authorization_codes[code] = {
            "client_id": "c1",
            "redirect_uri": "https://app.com/cb",
            "scope": "mcp:tools",
            "created_at": time.time() - 700,
            "expires_in": 600,
            "code_challenge": None,
            "user_id": "u1",
            "user_email": None,
            "resource": None,
        }
        req = MagicMock()
        req.headers = {"content-type": "application/json"}
        req.json = AsyncMock(return_value={"grant_type": "authorization_code", "code": code})
        response = await oauth_token_handler(req)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_pkce_required_but_missing_verifier_returns_400(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_token_handler, _authorization_codes

        verifier, challenge = _make_pkce_verifier()
        code = "pkce_required_code"
        _authorization_codes[code] = {
            "client_id": "c1",
            "redirect_uri": "https://app.com/cb",
            "scope": "mcp:tools",
            "created_at": time.time(),
            "expires_in": 600,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "user_id": "u1",
            "user_email": None,
            "resource": None,
        }
        req = MagicMock()
        req.headers = {"content-type": "application/json"}
        req.json = AsyncMock(return_value={"grant_type": "authorization_code", "code": code})
        response = await oauth_token_handler(req)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["error"] == "invalid_request"

    @pytest.mark.asyncio
    async def test_pkce_wrong_verifier_returns_400(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_token_handler, _authorization_codes

        verifier, challenge = _make_pkce_verifier()
        code = "pkce_bad_verifier_code"
        _authorization_codes[code] = {
            "client_id": "c1",
            "redirect_uri": "https://app.com/cb",
            "scope": "mcp:tools",
            "created_at": time.time(),
            "expires_in": 600,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "user_id": "u1",
            "user_email": None,
            "resource": None,
        }
        req = MagicMock()
        req.headers = {"content-type": "application/json"}
        req.json = AsyncMock(
            return_value={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": "wrong_verifier",
            }
        )
        response = await oauth_token_handler(req)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_client_credentials_no_auth_configured_issues_token(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_token_handler

        req = MagicMock()
        req.headers = {"content-type": "application/json"}
        req.json = AsyncMock(return_value={"grant_type": "client_credentials"})
        with patch("ii_agent.integrations.mcp_sse.oauth.is_auth_configured", return_value=False):
            with patch("ii_agent.integrations.mcp_sse.oauth.store_issued_token"):
                response = await oauth_token_handler(req)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert "access_token" in body
        assert body["token_type"] == "Bearer"

    @pytest.mark.asyncio
    async def test_client_credentials_with_invalid_credentials_returns_401(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_token_handler

        req = MagicMock()
        req.headers = {"content-type": "application/json"}
        req.json = AsyncMock(
            return_value={
                "grant_type": "client_credentials",
                "client_id": "bad_client",
                "client_secret": "bad_secret",
            }
        )
        with patch("ii_agent.integrations.mcp_sse.oauth.is_auth_configured", return_value=True):
            with patch(
                "ii_agent.integrations.mcp_sse.oauth.validate_client_credentials",
                return_value=False,
            ):
                response = await oauth_token_handler(req)
        assert response.status_code == 401
        body = json.loads(response.body)
        assert body["error"] == "invalid_client"

    @pytest.mark.asyncio
    async def test_basic_auth_header_parsed(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_token_handler

        credentials = base64.b64encode(b"myclient:mysecret").decode()
        req = MagicMock()
        req.headers = {
            "content-type": "application/json",
            "authorization": f"Basic {credentials}",
        }
        req.json = AsyncMock(return_value={"grant_type": "client_credentials"})
        with patch("ii_agent.integrations.mcp_sse.oauth.is_auth_configured", return_value=False):
            with patch("ii_agent.integrations.mcp_sse.oauth.store_issued_token"):
                response = await oauth_token_handler(req)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_form_encoded_content_type_parsed(self):
        from ii_agent.integrations.mcp_sse.oauth import oauth_token_handler

        form = {"grant_type": "client_credentials"}
        req = MagicMock()
        req.headers = {"content-type": "application/x-www-form-urlencoded"}
        req.form = AsyncMock(return_value=form)
        with patch("ii_agent.integrations.mcp_sse.oauth.is_auth_configured", return_value=False):
            with patch("ii_agent.integrations.mcp_sse.oauth.store_issued_token"):
                response = await oauth_token_handler(req)
        assert response.status_code == 200
