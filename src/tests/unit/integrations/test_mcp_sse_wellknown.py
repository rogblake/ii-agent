"""Unit tests for integrations/mcp_sse/wellknown.py.

Tests helper functions and (optionally) FastAPI route responses.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.skip("ii_agent.integrations.mcp_sse was removed during refactoring", allow_module_level=True)

from starlette.testclient import TestClient
from fastapi import FastAPI
from starlette.requests import Request

from ii_agent.integrations.mcp_sse.wellknown import (
    _get_mcp_base_url,
    _get_oauth_authorization_server_metadata,
    _get_openid_config,
    _get_protected_resource_metadata,
    wellknown_router,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(
    *,
    scheme: str = "https",
    netloc: str = "example.com",
    forwarded_proto: str | None = None,
    forwarded_host: str | None = None,
) -> Request:
    """Build a minimal Starlette Request mock."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [],
    }
    request = MagicMock(spec=Request)
    url_mock = MagicMock()
    url_mock.scheme = scheme
    url_mock.netloc = netloc
    request.url = url_mock

    base_url_mock = MagicMock()
    base_url_mock.__str__ = lambda _: f"{scheme}://{netloc}/"
    request.base_url = base_url_mock

    headers: dict[str, str] = {}
    if forwarded_proto:
        headers["x-forwarded-proto"] = forwarded_proto
    if forwarded_host:
        headers["x-forwarded-host"] = forwarded_host

    request.headers = headers
    return request


def _make_settings(mcp_api_url: str | None = None) -> MagicMock:
    settings = MagicMock()
    settings.mcp_api_url = mcp_api_url
    return settings


# ---------------------------------------------------------------------------
# _get_mcp_base_url
# ---------------------------------------------------------------------------


class TestGetMcpBaseUrl:
    def test_uses_mcp_api_url_when_set(self):
        settings = _make_settings(mcp_api_url="https://mcp.example.com")
        request = _make_request()
        result = _get_mcp_base_url(request, settings)
        assert result == "https://mcp.example.com/mcp"

    def test_mcp_api_url_already_ending_with_mcp(self):
        settings = _make_settings(mcp_api_url="https://mcp.example.com/mcp")
        request = _make_request()
        result = _get_mcp_base_url(request, settings)
        assert result == "https://mcp.example.com/mcp"

    def test_mcp_api_url_trailing_slash_stripped(self):
        settings = _make_settings(mcp_api_url="https://mcp.example.com/")
        request = _make_request()
        result = _get_mcp_base_url(request, settings)
        # trailing slash stripped, then /mcp appended
        assert result == "https://mcp.example.com/mcp"

    def test_uses_forwarded_headers(self):
        settings = _make_settings(mcp_api_url=None)
        request = _make_request(forwarded_proto="https", forwarded_host="proxy.example.com")
        result = _get_mcp_base_url(request, settings)
        assert result == "https://proxy.example.com/mcp"

    def test_forwarded_proto_only(self):
        settings = _make_settings(mcp_api_url=None)
        request = _make_request(forwarded_proto="http", netloc="fallback.com")
        result = _get_mcp_base_url(request, settings)
        assert result.startswith("http://")
        assert "/mcp" in result

    def test_forwarded_host_only(self):
        settings = _make_settings(mcp_api_url=None)
        request = _make_request(scheme="https", netloc="base.com", forwarded_host="custom.host.com")
        result = _get_mcp_base_url(request, settings)
        assert "custom.host.com" in result
        assert "/mcp" in result

    def test_fallback_to_base_url(self):
        settings = _make_settings(mcp_api_url=None)
        request = _make_request(scheme="https", netloc="app.example.com")
        result = _get_mcp_base_url(request, settings)
        assert result == "https://app.example.com/mcp"

    def test_comma_separated_forwarded_proto_uses_first(self):
        settings = _make_settings(mcp_api_url=None)
        request = _make_request(forwarded_proto="https, http", forwarded_host="a.com, b.com")
        result = _get_mcp_base_url(request, settings)
        assert result.startswith("https://a.com")


# ---------------------------------------------------------------------------
# _get_oauth_authorization_server_metadata
# ---------------------------------------------------------------------------


class TestGetOAuthAuthorizationServerMetadata:
    def _get_meta(self, mcp_api_url="https://mcp.example.com"):
        settings = _make_settings(mcp_api_url=mcp_api_url)
        request = _make_request()
        return _get_oauth_authorization_server_metadata(request, settings)

    def test_issuer_is_mcp_base(self):
        meta = self._get_meta()
        assert meta["issuer"] == "https://mcp.example.com/mcp"

    def test_authorization_endpoint_present(self):
        meta = self._get_meta()
        assert meta["authorization_endpoint"].endswith("/oauth/authorize")

    def test_token_endpoint_present(self):
        meta = self._get_meta()
        assert meta["token_endpoint"].endswith("/oauth/token")

    def test_registration_endpoint_present(self):
        meta = self._get_meta()
        assert meta["registration_endpoint"].endswith("/oauth/register")

    def test_grant_types_include_authorization_code(self):
        meta = self._get_meta()
        assert "authorization_code" in meta["grant_types_supported"]

    def test_scopes_include_mcp_tools(self):
        meta = self._get_meta()
        assert "mcp:tools" in meta["scopes_supported"]

    def test_code_challenge_methods_include_s256(self):
        meta = self._get_meta()
        assert "S256" in meta["code_challenge_methods_supported"]

    def test_service_documentation_field_present(self):
        meta = self._get_meta()
        assert "service_documentation" in meta

    def test_response_types_contains_code(self):
        meta = self._get_meta()
        assert "code" in meta["response_types_supported"]


# ---------------------------------------------------------------------------
# _get_openid_config
# ---------------------------------------------------------------------------


class TestGetOpenIdConfig:
    def _get_config(self, mcp_api_url="https://mcp.example.com"):
        settings = _make_settings(mcp_api_url=mcp_api_url)
        request = _make_request()
        return _get_openid_config(request, settings)

    def test_issuer_set(self):
        config = self._get_config()
        assert config["issuer"] == "https://mcp.example.com/mcp"

    def test_scopes_include_openid(self):
        config = self._get_config()
        assert "openid" in config["scopes_supported"]

    def test_response_types_include_token(self):
        config = self._get_config()
        assert "token" in config["response_types_supported"]


# ---------------------------------------------------------------------------
# _get_protected_resource_metadata
# ---------------------------------------------------------------------------


class TestGetProtectedResourceMetadata:
    def _get_meta(self, mcp_api_url="https://mcp.example.com"):
        settings = _make_settings(mcp_api_url=mcp_api_url)
        request = _make_request()
        return _get_protected_resource_metadata(request, settings)

    def test_resource_equals_mcp_base(self):
        meta = self._get_meta()
        assert meta["resource"] == "https://mcp.example.com/mcp"

    def test_authorization_servers_list(self):
        meta = self._get_meta()
        assert isinstance(meta["authorization_servers"], list)
        assert len(meta["authorization_servers"]) == 1

    def test_scopes_include_mcp_tools(self):
        meta = self._get_meta()
        assert "mcp:tools" in meta["scopes_supported"]

    def test_bearer_methods_include_header(self):
        meta = self._get_meta()
        assert "header" in meta["bearer_methods_supported"]


# ---------------------------------------------------------------------------
# Router endpoint integration tests
# ---------------------------------------------------------------------------


def _build_test_app() -> TestClient:
    """Build a FastAPI test client with mocked settings dependency."""
    from ii_agent.core.dependencies import SettingsDep

    app = FastAPI()

    mock_settings = _make_settings(mcp_api_url="https://mcp.test.com")

    app.dependency_overrides[SettingsDep] = lambda: mock_settings  # type: ignore[arg-type]

    app.include_router(wellknown_router)
    return TestClient(app)


class TestWellKnownRouterEndpoints:
    @pytest.fixture(autouse=True)
    def client(self):
        from ii_agent.core.dependencies import SettingsDep

        app = FastAPI()
        mock_settings = _make_settings(mcp_api_url="https://mcp.test.com")

        def override_settings():
            return mock_settings

        app.dependency_overrides[SettingsDep.__metadata__[0].dependency] = override_settings  # type: ignore[attr-defined]
        app.include_router(wellknown_router)
        self._client = TestClient(app, raise_server_exceptions=True)

    def test_oauth_protected_resource_returns_200(self):
        resp = self._client.get("/.well-known/oauth-protected-resource")
        assert resp.status_code == 200

    def test_oauth_protected_resource_has_resource_key(self):
        resp = self._client.get("/.well-known/oauth-protected-resource")
        data = resp.json()
        assert "resource" in data

    def test_oauth_authorization_server_returns_200(self):
        resp = self._client.get("/.well-known/oauth-authorization-server")
        assert resp.status_code == 200

    def test_oauth_authorization_server_has_issuer(self):
        resp = self._client.get("/.well-known/oauth-authorization-server")
        data = resp.json()
        assert "issuer" in data

    def test_openid_configuration_returns_200(self):
        resp = self._client.get("/.well-known/openid-configuration")
        assert resp.status_code == 200

    def test_mcp_path_variants_return_200(self):
        for path in [
            "/.well-known/oauth-protected-resource/mcp",
            "/.well-known/oauth-authorization-server/mcp",
            "/.well-known/openid-configuration/mcp",
        ]:
            resp = self._client.get(path)
            assert resp.status_code == 200, f"Path {path} returned {resp.status_code}"
