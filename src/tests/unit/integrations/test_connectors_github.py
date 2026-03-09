"""Unit tests for ii_agent.integrations.connectors.github."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.integrations.connectors.github import (
    GitHubConnector,
    INSTALLATION_TOKEN_EXPIRY_MINUTES,
    ConnectorData,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(
    *,
    github_app_id: str | None = "app-123",
    github_app_private_key: str | None = "private\nkey",
    github_client_id: str | None = "client-id",
    github_client_secret: str | None = "client-secret",
    github_redirect_uri: str = "https://app.local/callback",
    github_app_name: str | None = "my-app",
):
    return SimpleNamespace(
        oauth=SimpleNamespace(
            github_app_id=github_app_id,
            github_app_private_key=github_app_private_key,
            github_client_id=github_client_id,
            github_client_secret=github_client_secret,
            github_redirect_uri=github_redirect_uri,
            github_app_name=github_app_name,
        )
    )


def _make_async_response(payload=None, status_code: int = 200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload or {}
    response.raise_for_status = MagicMock()
    return response


def _make_http_client() -> AsyncMock:
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    return client


def test_generate_jwt_requires_app_id():
    connector = GitHubConnector(db_session=MagicMock())

    with patch(
        "ii_agent.integrations.connectors.github.get_settings",
        return_value=_settings(github_app_id=""),
    ):
        with pytest.raises(ValueError, match="GitHub App ID is not configured"):
            connector._generate_jwt()


def test_generate_jwt_requires_private_key():
    connector = GitHubConnector(db_session=MagicMock())
    with patch(
        "ii_agent.integrations.connectors.github.get_settings",
        return_value=_settings(github_app_private_key=""),
    ):
        with pytest.raises(ValueError, match="private key is not configured"):
            connector._generate_jwt()


def test_get_private_key_rewrites_newlines():
    connector = GitHubConnector(db_session=MagicMock())
    with patch(
        "ii_agent.integrations.connectors.github.get_settings",
        return_value=_settings(github_app_private_key="a\\n b"),
    ):
        assert connector._get_private_key() == "a\n b"


def test_is_github_app_configured_requires_id_and_key():
    connector = GitHubConnector(db_session=MagicMock())
    with patch(
        "ii_agent.integrations.connectors.github.get_settings",
        return_value=_settings(github_app_id="", github_app_private_key="key"),
    ):
        assert connector._is_github_app_configured() is False

    with patch(
        "ii_agent.integrations.connectors.github.get_settings",
        return_value=_settings(github_app_private_key=""),
    ):
        assert connector._is_github_app_configured() is False

    with patch(
        "ii_agent.integrations.connectors.github.get_settings",
        return_value=_settings(github_app_id="app", github_app_private_key="key"),
    ):
        assert connector._is_github_app_configured() is True


@pytest.mark.asyncio
async def test_get_auth_url_requires_credentials():
    connector = GitHubConnector(db_session=MagicMock())
    with patch(
        "ii_agent.integrations.connectors.github.get_settings",
        return_value=_settings(github_client_id="", github_client_secret="secret"),
    ):
        with pytest.raises(ValueError, match="not configured"):
            await connector.get_auth_url("state")


@pytest.mark.asyncio
async def test_get_auth_url_includes_scopes_and_redirect_uri():
    connector = GitHubConnector(db_session=MagicMock())
    with patch(
        "ii_agent.integrations.connectors.github.get_settings",
        return_value=_settings(
            github_client_id="id",
            github_client_secret="secret",
            github_redirect_uri="https://default.cb/callback",
        ),
    ):
        default_url = await connector.get_auth_url("state")
        custom_url = await connector.get_auth_url("state", redirect_uri="https://custom/cb")

        assert "read%3Auser" in default_url
        assert "scope=read%3Auser+user%3Aemail+repo" in default_url
        assert "https%3A%2F%2Fdefault.cb%2Fcallback" in default_url
        assert "https%3A%2F%2Fcustom%2Fcb" in custom_url


@pytest.mark.asyncio
async def test_get_installation_id_for_user_find_and_missing():
    connector = GitHubConnector(db_session=MagicMock())
    client = _make_http_client()
    client.get = AsyncMock(
        return_value=_make_async_response(
            [
                {"id": 1, "account": {"login": "someone"}},
                {"id": 99, "account": {"login": "Alice"}},
            ]
        )
    )

    with (
        patch("ii_agent.integrations.connectors.github.get_settings", return_value=_settings()),
        patch("ii_agent.integrations.connectors.github.httpx.AsyncClient", return_value=client),
        patch("ii_agent.integrations.connectors.github.jwt.encode", return_value="jwt"),
    ):
        assert await connector._get_installation_id_for_user("alice") == 99
        assert await connector._get_installation_id_for_user("missing") is None


@pytest.mark.asyncio
async def test_get_installation_id_for_user_errors_return_none():
    connector = GitHubConnector(db_session=MagicMock())
    with patch.object(
        connector,
        "_generate_jwt",
        side_effect=RuntimeError("boom"),
    ):
        assert await connector._get_installation_id_for_user("alice") is None


@pytest.mark.asyncio
async def test_generate_installation_token_parses_expiry_and_fallback():
    connector = GitHubConnector(db_session=MagicMock())
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expiry = (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")

    client = _make_http_client()
    token_response = _make_async_response({"token": "with-exp", "expires_at": expiry})
    client.post = AsyncMock(return_value=token_response)

    with (
        patch("ii_agent.integrations.connectors.github.get_settings", return_value=_settings()),
        patch("ii_agent.integrations.connectors.github.jwt.encode", return_value="jwt"),
        patch("ii_agent.integrations.connectors.github.httpx.AsyncClient", return_value=client),
    ):
        data = await connector._generate_installation_token(1)
        assert data.access_token == "with-exp"
        assert data.token_expiry is not None
        assert data.token_expiry.tzinfo is not None

    fallback_client = _make_http_client()
    fallback_client.post = AsyncMock(
        return_value=_make_async_response({"token": "without-exp"})
    )
    with (
        patch("ii_agent.integrations.connectors.github.get_settings", return_value=_settings()),
        patch("ii_agent.integrations.connectors.github.jwt.encode", return_value="jwt"),
        patch("ii_agent.integrations.connectors.github.httpx.AsyncClient", return_value=fallback_client),
    ):
        data = await connector._generate_installation_token(1)
        assert data.access_token == "without-exp"
        assert data.token_expiry is not None
        expected = datetime.now(timezone.utc) + timedelta(
            minutes=INSTALLATION_TOKEN_EXPIRY_MINUTES
        )
        assert abs((data.token_expiry - expected).total_seconds()) < 120


@pytest.mark.asyncio
async def test_handle_callback_uses_user_token_when_app_not_configured():
    connector = GitHubConnector(db_session=MagicMock())
    client = _make_http_client()
    client.post = AsyncMock(
        return_value=_make_async_response(
            {"access_token": "user-token", "scope": "repo,user:email"}
        )
    )
    client.get = AsyncMock(
        return_value=_make_async_response(
            {
                "login": "alice",
                "name": "Alice",
                "email": "a@b",
                "avatar_url": "https://avatar",
            }
        )
    )

    with (
        patch("ii_agent.integrations.connectors.github.get_settings", return_value=_settings()),
        patch("ii_agent.integrations.connectors.github.httpx.AsyncClient", return_value=client),
        patch.object(GitHubConnector, "_is_github_app_configured", return_value=False),
    ):
        result = await connector.handle_callback("code", "state")
        assert result.access_token == "user-token"
        assert result.metadata["app_type"] == "oauth_app"
        assert result.metadata["scopes_granted"] == ["repo", "user:email"]


@pytest.mark.asyncio
async def test_handle_callback_uses_installation_token_when_available():
    connector = GitHubConnector(db_session=MagicMock())
    client = _make_http_client()
    client.post = AsyncMock(
        return_value=_make_async_response({"access_token": "user-token", "scope": "repo"})
    )
    client.get = AsyncMock(
        return_value=_make_async_response(
            {
                "login": "alice",
                "name": "Alice",
                "email": "a@b",
                "avatar_url": "https://avatar",
            }
        )
    )

    with (
        patch("ii_agent.integrations.connectors.github.get_settings", return_value=_settings()),
        patch("ii_agent.integrations.connectors.github.httpx.AsyncClient", return_value=client),
        patch.object(GitHubConnector, "_is_github_app_configured", return_value=True),
        patch.object(
            GitHubConnector,
            "_get_installation_id_for_user",
            AsyncMock(return_value=77),
        ),
        patch.object(
            GitHubConnector,
            "_generate_installation_token",
            AsyncMock(
                return_value=ConnectorData(
                    access_token="install-token",
                    token_expiry=datetime.now(timezone.utc) + timedelta(minutes=10),
                )
            ),
        ),
    ):
        result = await connector.handle_callback("code", "state")
        assert result.access_token == "install-token"
        assert result.metadata["installation_id"] == 77
        assert result.metadata["app_type"] == "github_app_installation"


@pytest.mark.asyncio
async def test_handle_callback_falls_back_when_no_installation_configured():
    connector = GitHubConnector(db_session=MagicMock())
    client = _make_http_client()
    client.post = AsyncMock(
        return_value=_make_async_response({"access_token": "user-token", "scope": "repo"})
    )
    client.get = AsyncMock(
        return_value=_make_async_response(
            {
                "login": "alice",
                "name": "Alice",
                "email": "a@b",
                "avatar_url": "https://avatar",
            }
        )
    )

    with (
        patch("ii_agent.integrations.connectors.github.get_settings", return_value=_settings()),
        patch("ii_agent.integrations.connectors.github.httpx.AsyncClient", return_value=client),
        patch.object(GitHubConnector, "_is_github_app_configured", return_value=True),
        patch.object(
            GitHubConnector,
            "_get_installation_id_for_user",
            AsyncMock(return_value=None),
        ),
    ):
        result = await connector.handle_callback("code", "state")
        assert result.access_token == "user-token"
        assert result.metadata["app_type"] == "github_app_not_installed"


@pytest.mark.asyncio
async def test_handle_callback_raises_when_oauth_exchange_fails():
    connector = GitHubConnector(db_session=MagicMock())
    client = _make_http_client()
    client.post = AsyncMock(
        return_value=_make_async_response(
            {"error": "bad_code", "error_description": "invalid code"}
        )
    )

    with (
        patch("ii_agent.integrations.connectors.github.get_settings", return_value=_settings()),
        patch("ii_agent.integrations.connectors.github.httpx.AsyncClient", return_value=client),
    ):
        with pytest.raises(Exception, match="invalid code"):
            await connector.handle_callback("code", "state")


@pytest.mark.asyncio
async def test_refresh_access_token_installation_success_and_failure():
    connector = GitHubConnector(db_session=MagicMock())
    stored = SimpleNamespace(connector_metadata={"installation_id": 12})

    with (
        patch.object(
            GitHubConnector,
            "_is_github_app_configured",
            return_value=True,
        ),
        patch.object(
            GitHubConnector,
            "_generate_installation_token",
            AsyncMock(
                return_value=ConnectorData(
                    access_token="new-token",
                    token_expiry=datetime.now(timezone.utc),
                )
            ),
        ),
    ):
        updated = await connector.refresh_access_token(stored)
        assert updated.access_token == "new-token"

    with (
        patch.object(
            GitHubConnector,
            "_is_github_app_configured",
            return_value=True,
        ),
        patch.object(
            GitHubConnector,
            "_generate_installation_token",
            AsyncMock(side_effect=RuntimeError("fail")),
        ),
    ):
        with pytest.raises(Exception, match="Please reconnect"):
            await connector.refresh_access_token(stored)


@pytest.mark.asyncio
async def test_refresh_access_token_without_installation_keeps_existing_token():
    connector = GitHubConnector(db_session=MagicMock())
    stored = SimpleNamespace(connector_metadata={"installation_id": None}, access_token="static")

    with patch.object(GitHubConnector, "_is_github_app_configured", return_value=True):
        updated = await connector.refresh_access_token(stored)
        assert updated.access_token == "static"


@pytest.mark.asyncio
async def test_validate_token_returns_true_false():
    connector = GitHubConnector(db_session=MagicMock())

    ok_client = _make_http_client()
    ok_client.get = AsyncMock(return_value=_make_async_response({}, status_code=200))
    bad_client = _make_http_client()
    bad_client.get = AsyncMock(return_value=_make_async_response({}, status_code=401))

    with patch("ii_agent.integrations.connectors.github.httpx.AsyncClient", return_value=ok_client):
        assert await connector.validate_token("token") is True

    with patch(
        "ii_agent.integrations.connectors.github.httpx.AsyncClient",
        return_value=bad_client,
    ):
        assert await connector.validate_token("token") is False


@pytest.mark.asyncio
async def test_revoke_access_returns_true():
    connector = GitHubConnector(db_session=MagicMock())
    assert await connector.revoke_access(SimpleNamespace(id="id")) is True


@pytest.mark.asyncio
async def test_get_valid_token_refreshes_when_token_expiring():
    connector = GitHubConnector(db_session=MagicMock())
    connector.get_connector = AsyncMock(
        return_value=SimpleNamespace(
            access_token="old",
            token_expiry=datetime.now(timezone.utc),
            connector_metadata={"installation_id": 7},
            updated_at=None,
        )
    )
    connector.db_session = AsyncMock()
    connector.db_session.commit = AsyncMock()
    connector.db_session.refresh = AsyncMock()
    connector.refresh_access_token = AsyncMock(
        return_value=ConnectorData(access_token="new-token", token_expiry=datetime.now(timezone.utc))
    )

    with patch.object(GitHubConnector, "_is_github_app_configured", return_value=True):
        token = await connector.get_valid_token("user-1")

    assert token == "new-token"
    connector.refresh_access_token.assert_awaited_once()
    connector.db_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_valid_token_returns_none_when_not_connected():
    connector = GitHubConnector(db_session=MagicMock())
    connector.get_connector = AsyncMock(return_value=None)
    assert await connector.get_valid_token("missing") is None


@pytest.mark.asyncio
async def test_get_repositories_returns_list_and_handles_401():
    connector = GitHubConnector(db_session=MagicMock())
    connector.get_valid_token = AsyncMock(return_value="token")

    ok_client = _make_http_client()
    ok_client.get = AsyncMock(return_value=_make_async_response([{"name": "repo-1"}]))
    with patch("ii_agent.integrations.connectors.github.httpx.AsyncClient", return_value=ok_client):
        repos = await connector.get_repositories("user-1", per_page=20)
        assert repos == [{"name": "repo-1"}]

    unauthorized = _make_http_client()
    unauthorized.get = AsyncMock(return_value=_make_async_response({}, status_code=401))
    with patch(
        "ii_agent.integrations.connectors.github.httpx.AsyncClient",
        return_value=unauthorized,
    ):
        with pytest.raises(Exception, match="token is invalid"):
            await connector.get_repositories("user-1")


@pytest.mark.asyncio
async def test_get_auth_url_stateful_scopes_and_default_redirect():
    connector = GitHubConnector(db_session=MagicMock())
    with patch(
        "ii_agent.integrations.connectors.github.get_settings",
        return_value=_settings(
            github_client_id="id",
            github_client_secret="secret",
            github_redirect_uri="https://default",
        ),
    ):
        url = await connector.get_auth_url("state")
        assert "github.com/login/oauth/authorize" in url
        assert "scope=read%3Auser+user%3Aemail+repo" in url
        assert "redirect_uri=https%3A%2F%2Fdefault" in url
