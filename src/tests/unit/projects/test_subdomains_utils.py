"""Unit tests for projects/subdomains/utils.py - validate_subdomain and CloudflareKVService."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.projects.subdomains.utils import (
    RESERVED_SUBDOMAINS,
    CloudflareKVConfig,
    CloudflareKVService,
    SubdomainStatus,
    validate_subdomain,
)


# ---------------------------------------------------------------------------
# validate_subdomain
# ---------------------------------------------------------------------------


class TestValidateSubdomain:
    """Tests for the validate_subdomain() helper function."""

    def test_valid_simple_subdomain(self):
        """A standard alphanumeric subdomain passes validation."""
        valid, error = validate_subdomain("myapp")
        assert valid is True
        assert error is None

    def test_valid_subdomain_with_numbers(self):
        """Subdomains with digits are valid."""
        valid, error = validate_subdomain("app123")
        assert valid is True
        assert error is None

    def test_valid_subdomain_with_hyphens(self):
        """Subdomains containing hyphens are valid."""
        valid, error = validate_subdomain("my-cool-app")
        assert valid is True
        assert error is None

    def test_too_short_subdomain(self):
        """Single-character subdomains are rejected."""
        valid, error = validate_subdomain("a")
        assert valid is False
        assert "at least 2" in error

    def test_empty_string_is_too_short(self):
        """Empty string is rejected."""
        valid, error = validate_subdomain("")
        assert valid is False
        assert error is not None

    def test_too_long_subdomain(self):
        """Subdomain longer than 63 chars is rejected."""
        long_name = "a" * 64
        valid, error = validate_subdomain(long_name)
        assert valid is False
        assert "63" in error

    def test_exactly_63_chars_is_valid(self):
        """Subdomain of exactly 63 characters is at the boundary and valid."""
        name = "a" * 63
        valid, error = validate_subdomain(name)
        assert valid is True
        assert error is None

    def test_uppercase_is_lowercased_internally(self):
        """Uppercase input is lowercased and can pass validation."""
        valid, error = validate_subdomain("MyApp")
        assert valid is True
        assert error is None

    def test_leading_hyphen_is_invalid(self):
        """A subdomain starting with a hyphen is invalid."""
        valid, error = validate_subdomain("-myapp")
        assert valid is False
        assert error is not None

    def test_trailing_hyphen_is_invalid(self):
        """A subdomain ending with a hyphen is invalid."""
        valid, error = validate_subdomain("myapp-")
        assert valid is False
        assert error is not None

    def test_underscore_is_invalid(self):
        """Underscores are not allowed."""
        valid, error = validate_subdomain("my_app")
        assert valid is False
        assert error is not None

    def test_dot_is_invalid(self):
        """Dots are not allowed in a single label subdomain."""
        valid, error = validate_subdomain("my.app")
        assert valid is False
        assert error is not None

    def test_special_characters_invalid(self):
        """Special characters like @ are rejected."""
        valid, error = validate_subdomain("my@app")
        assert valid is False
        assert error is not None

    def test_reserved_www(self):
        """'www' is a reserved subdomain."""
        valid, error = validate_subdomain("www")
        assert valid is False
        assert "reserved" in error.lower()

    def test_reserved_api(self):
        """'api' is reserved."""
        valid, error = validate_subdomain("api")
        assert valid is False

    def test_reserved_admin(self):
        """'admin' is reserved."""
        valid, error = validate_subdomain("admin")
        assert valid is False

    def test_reserved_app(self):
        """'app' is reserved."""
        valid, error = validate_subdomain("app")
        assert valid is False

    def test_reserved_login(self):
        """'login' is reserved."""
        valid, error = validate_subdomain("login")
        assert valid is False

    def test_reserved_dashboard(self):
        """'dashboard' is reserved."""
        valid, error = validate_subdomain("dashboard")
        assert valid is False

    def test_all_reserved_subdomains_reject(self):
        """Every reserved subdomain must be rejected."""
        for name in RESERVED_SUBDOMAINS:
            valid, _ = validate_subdomain(name)
            assert valid is False, f"'{name}' should be reserved but passed validation"

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace is stripped before validation."""
        valid, error = validate_subdomain("  myapp  ")
        assert valid is True
        assert error is None

    def test_numeric_only_subdomain_valid(self):
        """Numeric-only subdomains are structurally valid (not reserved)."""
        valid, error = validate_subdomain("12")
        assert valid is True
        assert error is None


# ---------------------------------------------------------------------------
# CloudflareKVConfig
# ---------------------------------------------------------------------------


class TestCloudflareKVConfig:
    """Tests for CloudflareKVConfig.from_env()."""

    def test_from_env_success(self, monkeypatch):
        """All required env vars present -> returns config object."""
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token123")
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct456")
        monkeypatch.setenv("CLOUDFLARE_KV_NAMESPACE_ID", "ns789")
        monkeypatch.setenv("CLOUDFLARE_BASE_DOMAIN", "example.com")

        config = CloudflareKVConfig.from_env()
        assert config.api_token == "token123"
        assert config.account_id == "acct456"
        assert config.kv_namespace_id == "ns789"
        assert config.base_domain == "example.com"

    def test_from_env_missing_api_token(self, monkeypatch):
        """Missing CLOUDFLARE_API_TOKEN raises ValueError."""
        monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct456")
        monkeypatch.setenv("CLOUDFLARE_KV_NAMESPACE_ID", "ns789")
        monkeypatch.setenv("CLOUDFLARE_BASE_DOMAIN", "example.com")

        with pytest.raises(ValueError, match="CLOUDFLARE_API_TOKEN"):
            CloudflareKVConfig.from_env()

    def test_from_env_missing_account_id(self, monkeypatch):
        """Missing CLOUDFLARE_ACCOUNT_ID raises ValueError."""
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token123")
        monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
        monkeypatch.setenv("CLOUDFLARE_KV_NAMESPACE_ID", "ns789")
        monkeypatch.setenv("CLOUDFLARE_BASE_DOMAIN", "example.com")

        with pytest.raises(ValueError, match="CLOUDFLARE_ACCOUNT_ID"):
            CloudflareKVConfig.from_env()

    def test_from_env_missing_kv_namespace_id(self, monkeypatch):
        """Missing CLOUDFLARE_KV_NAMESPACE_ID raises ValueError."""
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token123")
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct456")
        monkeypatch.delenv("CLOUDFLARE_KV_NAMESPACE_ID", raising=False)
        monkeypatch.setenv("CLOUDFLARE_BASE_DOMAIN", "example.com")

        with pytest.raises(ValueError, match="CLOUDFLARE_KV_NAMESPACE_ID"):
            CloudflareKVConfig.from_env()

    def test_from_env_missing_base_domain(self, monkeypatch):
        """Missing CLOUDFLARE_BASE_DOMAIN raises ValueError."""
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token123")
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct456")
        monkeypatch.setenv("CLOUDFLARE_KV_NAMESPACE_ID", "ns789")
        monkeypatch.delenv("CLOUDFLARE_BASE_DOMAIN", raising=False)

        with pytest.raises(ValueError, match="CLOUDFLARE_BASE_DOMAIN"):
            CloudflareKVConfig.from_env()


# ---------------------------------------------------------------------------
# CloudflareKVService helpers
# ---------------------------------------------------------------------------


def _make_config() -> CloudflareKVConfig:
    return CloudflareKVConfig(
        api_token="tok",
        account_id="acct",
        kv_namespace_id="ns",
        base_domain="iiapp.dev",
    )


def _make_service() -> CloudflareKVService:
    return CloudflareKVService(_make_config())


def _fake_response(status_code: int, body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    if body is not None:
        resp.json.return_value = body
        resp.text = json.dumps(body)
    else:
        resp.json.side_effect = Exception("no body")
        resp.text = ""
    return resp


class TestCloudflareKVServiceClientLazy:
    """Client is lazily created on first property access."""

    def test_client_is_not_created_on_init(self):
        svc = _make_service()
        assert svc._client is None

    def test_client_is_created_on_first_access(self):
        svc = _make_service()
        client = svc.client
        assert client is not None
        assert svc._client is client

    def test_client_is_reused_on_second_access(self):
        svc = _make_service()
        c1 = svc.client
        c2 = svc.client
        assert c1 is c2


class TestCloudflareKVServiceValidateSubdomain:
    """create_subdomain returns an error result for invalid subdomains."""

    @pytest.mark.asyncio
    async def test_create_subdomain_invalid_returns_failure(self):
        svc = _make_service()
        # Inject a fake client that should never be called
        mock_client = AsyncMock()
        svc._client = mock_client

        result = await svc.create_subdomain("-invalid", "https://cloud.run")
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_create_subdomain_reserved_returns_failure(self):
        svc = _make_service()
        result = await svc.create_subdomain("www", "https://cloud.run")
        assert result.success is False
        assert "reserved" in (result.error or "").lower()


class TestCloudflareKVServiceGetKVValue:
    """_get_kv_value returns dict or None based on HTTP responses."""

    @pytest.mark.asyncio
    async def test_get_kv_value_returns_none_on_404(self):
        svc = _make_service()
        mock_client = AsyncMock()
        mock_client.get.return_value = _fake_response(404)
        svc._client = mock_client

        result = await svc._get_kv_value("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_kv_value_returns_none_on_non_200_non_404(self):
        svc = _make_service()
        mock_client = AsyncMock()
        mock_client.get.return_value = _fake_response(500)
        svc._client = mock_client

        result = await svc._get_kv_value("key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_kv_value_returns_dict_on_200(self):
        svc = _make_service()
        mock_client = AsyncMock()
        body = {"cloud_run_url": "https://x.run.app", "project_id": "p1"}
        mock_client.get.return_value = _fake_response(200, body)
        svc._client = mock_client

        result = await svc._get_kv_value("key")
        assert result == body

    @pytest.mark.asyncio
    async def test_get_kv_value_falls_back_to_text_on_json_error(self):
        svc = _make_service()
        mock_client = AsyncMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.side_effect = Exception("bad json")
        resp.text = "https://fallback.run"
        mock_client.get.return_value = resp
        svc._client = mock_client

        result = await svc._get_kv_value("key")
        assert result == {"cloud_run_url": "https://fallback.run"}


class TestCloudflareKVServiceCreateSubdomain:
    """create_subdomain success and error paths."""

    @pytest.mark.asyncio
    async def test_create_new_subdomain_success(self):
        svc = _make_service()
        mock_client = AsyncMock()
        # _get_kv_value returns None (does not exist)
        mock_client.get.return_value = _fake_response(404)
        # PUT succeeds
        mock_client.put.return_value = _fake_response(200, {"success": True})
        svc._client = mock_client

        result = await svc.create_subdomain("myapp", "https://cloud.run/app")
        assert result.success is True
        assert result.subdomain == "myapp"
        assert result.full_domain == "myapp.iiapp.dev"
        assert result.status == SubdomainStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_create_subdomain_updates_if_exists(self):
        svc = _make_service()
        mock_client = AsyncMock()
        # _get_kv_value says it exists
        existing = {"cloud_run_url": "https://old.run", "project_id": "p1"}
        mock_client.get.return_value = _fake_response(200, existing)
        # Update PUT also succeeds
        mock_client.put.return_value = _fake_response(200, {"success": True})
        svc._client = mock_client

        result = await svc.create_subdomain("myapp", "https://new.run")
        assert result.success is True
        assert result.cloud_run_url == "https://new.run"

    @pytest.mark.asyncio
    async def test_create_subdomain_kv_write_failure(self):
        svc = _make_service()
        mock_client = AsyncMock()
        mock_client.get.return_value = _fake_response(404)
        mock_client.put.return_value = _fake_response(
            422, {"errors": [{"message": "quota exceeded"}]}
        )
        svc._client = mock_client

        result = await svc.create_subdomain("myapp", "https://cloud.run")
        assert result.success is False
        assert "quota exceeded" in (result.error or "")

    @pytest.mark.asyncio
    async def test_create_subdomain_network_exception_returns_failure(self):
        svc = _make_service()
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("network error")
        svc._client = mock_client

        result = await svc.create_subdomain("myapp", "https://cloud.run")
        assert result.success is False
        assert result.error is not None


class TestCloudflareKVServiceDeleteSubdomain:
    """delete_subdomain success and failure paths."""

    @pytest.mark.asyncio
    async def test_delete_subdomain_success(self):
        svc = _make_service()
        mock_client = AsyncMock()
        mock_client.delete.return_value = _fake_response(200)
        svc._client = mock_client

        result = await svc.delete_subdomain("myapp")
        assert result.success is True
        assert result.status == SubdomainStatus.DELETED

    @pytest.mark.asyncio
    async def test_delete_subdomain_204_success(self):
        svc = _make_service()
        mock_client = AsyncMock()
        mock_client.delete.return_value = _fake_response(204)
        svc._client = mock_client

        result = await svc.delete_subdomain("myapp")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_delete_subdomain_non_200_failure(self):
        svc = _make_service()
        mock_client = AsyncMock()
        mock_client.delete.return_value = _fake_response(404)
        svc._client = mock_client

        result = await svc.delete_subdomain("myapp")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_delete_subdomain_exception_returns_failure(self):
        svc = _make_service()
        mock_client = AsyncMock()
        mock_client.delete.side_effect = Exception("timeout")
        svc._client = mock_client

        result = await svc.delete_subdomain("myapp")
        assert result.success is False
        assert result.error is not None


class TestCloudflareKVServiceGetSubdomain:
    """get_subdomain fetches and returns details."""

    @pytest.mark.asyncio
    async def test_get_subdomain_found(self):
        svc = _make_service()
        mock_client = AsyncMock()
        body = {"cloud_run_url": "https://x.run", "project_id": "p1"}
        mock_client.get.return_value = _fake_response(200, body)
        svc._client = mock_client

        result = await svc.get_subdomain("myapp")
        assert result.success is True
        assert result.cloud_run_url == "https://x.run"

    @pytest.mark.asyncio
    async def test_get_subdomain_not_found(self):
        svc = _make_service()
        mock_client = AsyncMock()
        mock_client.get.return_value = _fake_response(404)
        svc._client = mock_client

        result = await svc.get_subdomain("myapp")
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_get_subdomain_exception_returns_failure(self):
        svc = _make_service()
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("unexpected")
        svc._client = mock_client

        result = await svc.get_subdomain("myapp")
        assert result.success is False


class TestCloudflareKVServiceCheckAvailability:
    """check_availability validates and checks KV."""

    @pytest.mark.asyncio
    async def test_check_availability_invalid_subdomain(self):
        svc = _make_service()
        available, error = await svc.check_availability("-bad")
        assert available is False
        assert error is not None

    @pytest.mark.asyncio
    async def test_check_availability_taken(self):
        svc = _make_service()
        mock_client = AsyncMock()
        mock_client.get.return_value = _fake_response(200, {"cloud_run_url": "https://x.run"})
        svc._client = mock_client

        available, error = await svc.check_availability("taken")
        assert available is False
        assert "taken" in error.lower()

    @pytest.mark.asyncio
    async def test_check_availability_free(self):
        svc = _make_service()
        mock_client = AsyncMock()
        mock_client.get.return_value = _fake_response(404)
        svc._client = mock_client

        available, error = await svc.check_availability("freename")
        assert available is True
        assert error is None


class TestCloudflareKVServiceUpdateSubdomain:
    """update_subdomain merges existing fields and writes new ones."""

    @pytest.mark.asyncio
    async def test_update_subdomain_preserves_existing_project_id(self):
        svc = _make_service()
        mock_client = AsyncMock()
        existing = {
            "cloud_run_url": "old",
            "project_id": "orig-proj",
            "user_id": "u1",
            "created_at": "2024-01-01T00:00:00Z",
        }
        mock_client.get.return_value = _fake_response(200, existing)
        mock_client.put.return_value = _fake_response(200)
        svc._client = mock_client

        result = await svc.update_subdomain("myapp", "https://new.run")
        assert result.success is True
        # Verify that PUT was called with JSON body containing old project_id
        put_call_args = mock_client.put.call_args
        sent_body = json.loads(put_call_args[1]["content"])
        assert sent_body["project_id"] == "orig-proj"

    @pytest.mark.asyncio
    async def test_update_subdomain_failure(self):
        svc = _make_service()
        mock_client = AsyncMock()
        mock_client.get.return_value = _fake_response(404)
        mock_client.put.return_value = _fake_response(500)
        svc._client = mock_client

        result = await svc.update_subdomain("myapp", "https://new.run")
        assert result.success is False


class TestCloudflareKVServiceClose:
    """close() cleans up the HTTP client."""

    @pytest.mark.asyncio
    async def test_close_clears_client(self):
        svc = _make_service()
        mock_client = AsyncMock()
        svc._client = mock_client

        await svc.close()
        mock_client.aclose.assert_called_once()
        assert svc._client is None

    @pytest.mark.asyncio
    async def test_close_is_noop_when_no_client(self):
        svc = _make_service()
        # Should not raise
        await svc.close()
