"""Unit tests for integrations/connectors/router.py - endpoint logic and helper functions."""

from __future__ import annotations

import sys
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# The package __init__.py re-exports the APIRouter instance as ``router``,
# which shadows the ``router.py`` *module* when Python resolves dotted
# attribute paths.  ``patch("ii_agent.integrations.connectors.router.X")``
# therefore fails because it finds the APIRouter object, not the module.
#
# Work-around: grab the real module object from ``sys.modules`` (populated
# during import) and use ``patch.object(router_module, "X")`` everywhere.
import ii_agent.integrations.connectors  # noqa: F401  – ensures router module is loaded

_router_module = sys.modules["ii_agent.integrations.connectors.router"]

from ii_agent.integrations.connectors.router import (
    _create_state_token,
    _verify_state_token,
    ConnectorAuthUrlResponse,
    ConnectorCallbackRequest,
    ConnectorStatusResponse,
    GitHubAppConfigResponse,
    GitHubRepositoriesResponse,
    GitHubRepository,
    GoogleDrivePickerConfigResponse,
)
from ii_agent.integrations.connectors.exceptions import (
    ConnectorStateError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_settings(secret: str = "test-session-secret"):
    settings = MagicMock()
    settings.oauth.session_secret_key = secret
    return settings


def _make_fake_user(user_id: str = "user-1"):
    user = MagicMock()
    user.id = user_id
    return user


# ---------------------------------------------------------------------------
# _create_state_token
# ---------------------------------------------------------------------------


class TestCreateStateToken:
    def test_returns_non_empty_string(self):
        with patch.object(_router_module, "get_settings", return_value=_mock_settings()):
            token = _create_state_token("user-1", "google_drive")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_includes_frontend_url_when_provided(self):
        with patch.object(_router_module, "get_settings", return_value=_mock_settings()):
            t1 = _create_state_token("user-1", "google_drive")
            t2 = _create_state_token("user-1", "google_drive", frontend_url="https://app.io")
        assert t1 != t2

    def test_includes_redirect_uri_when_provided(self):
        with patch.object(_router_module, "get_settings", return_value=_mock_settings()):
            t1 = _create_state_token("user-1", "github")
            t2 = _create_state_token("user-1", "github", redirect_uri="https://redir.io/callback")
        assert t1 != t2

    def test_different_users_produce_different_tokens(self):
        with patch.object(_router_module, "get_settings", return_value=_mock_settings()):
            t1 = _create_state_token("user-1", "google_drive")
            t2 = _create_state_token("user-2", "google_drive")
        assert t1 != t2

    def test_different_connector_types_produce_different_tokens(self):
        with patch.object(_router_module, "get_settings", return_value=_mock_settings()):
            t1 = _create_state_token("user-1", "google_drive")
            t2 = _create_state_token("user-1", "github")
        assert t1 != t2


# ---------------------------------------------------------------------------
# _verify_state_token
# ---------------------------------------------------------------------------


class TestVerifyStateToken:
    def test_valid_token_returns_data(self):
        with patch.object(_router_module, "get_settings", return_value=_mock_settings()):
            token = _create_state_token("user-1", "google_drive")
            data = _verify_state_token(token, "user-1")

        assert data["user_id"] == "user-1"
        assert data["connector"] == "google_drive"

    def test_wrong_user_id_raises(self):
        with patch.object(_router_module, "get_settings", return_value=_mock_settings()):
            token = _create_state_token("user-1", "google_drive")
            with pytest.raises(ConnectorStateError):
                _verify_state_token(token, "user-2")

    def test_tampered_token_raises(self):
        with patch.object(_router_module, "get_settings", return_value=_mock_settings()):
            with pytest.raises(ConnectorStateError):
                _verify_state_token("invalid.token.here", "user-1")

    def test_empty_token_raises(self):
        with patch.object(_router_module, "get_settings", return_value=_mock_settings()):
            with pytest.raises(ConnectorStateError):
                _verify_state_token("", "user-1")

    def test_includes_frontend_url_in_data(self):
        with patch.object(_router_module, "get_settings", return_value=_mock_settings()):
            token = _create_state_token("user-1", "github", frontend_url="https://myapp.io")
            data = _verify_state_token(token, "user-1")

        assert data.get("frontend_url") == "https://myapp.io"

    def test_round_trip_with_redirect_uri(self):
        with patch.object(_router_module, "get_settings", return_value=_mock_settings()):
            token = _create_state_token("user-1", "github", redirect_uri="https://cb.example.com")
            data = _verify_state_token(token, "user-1")

        assert data.get("redirect_uri") == "https://cb.example.com"


# ---------------------------------------------------------------------------
# Response model validation
# ---------------------------------------------------------------------------


class TestResponseModels:
    def test_connector_auth_url_response_valid(self):
        resp = ConnectorAuthUrlResponse(auth_url="https://auth.google.com/oauth", state="abc123")
        assert resp.auth_url == "https://auth.google.com/oauth"
        assert resp.state == "abc123"

    def test_connector_status_response_defaults(self):
        resp = ConnectorStatusResponse(is_connected=False, connector_type="github")
        assert resp.metadata is None
        assert resp.access_token is None

    def test_connector_status_response_with_metadata(self):
        resp = ConnectorStatusResponse(
            is_connected=True,
            connector_type="google_drive",
            metadata={"user_email": "user@example.com"},
            access_token="ya29.token",
        )
        assert resp.metadata["user_email"] == "user@example.com"

    def test_google_drive_picker_config_response(self):
        resp = GoogleDrivePickerConfigResponse(
            is_connected=True,
            access_token="ya29.token",
            developer_key="AIzaSy...",
            app_id="123456",
        )
        assert resp.is_connected is True

    def test_github_app_config_response_defaults(self):
        resp = GitHubAppConfigResponse()
        assert resp.app_name is None
        assert resp.installation_url is None

    def test_github_repository_response(self):
        repo = GitHubRepository(
            id=12345,
            name="my-repo",
            full_name="user/my-repo",
            owner="user",
            private=False,
            html_url="https://github.com/user/my-repo",
            default_branch="main",
        )
        assert repo.id == 12345
        assert repo.private is False
        assert repo.description is None

    def test_github_repositories_response_empty(self):
        resp = GitHubRepositoriesResponse(repositories=[])
        assert resp.repositories == []


# ---------------------------------------------------------------------------
# get_google_drive_auth_url (endpoint logic)
# ---------------------------------------------------------------------------


class TestGetGoogleDriveAuthUrl:
    @pytest.mark.asyncio
    async def test_returns_auth_url_response(self):
        from ii_agent.integrations.connectors.router import get_google_drive_auth_url

        mock_connector = AsyncMock()
        mock_connector.get_auth_url = AsyncMock(return_value="https://accounts.google.com/o/oauth2")

        with (
            patch.object(_router_module.ConnectorFactory, "create", return_value=mock_connector),
            patch.object(_router_module, "get_settings", return_value=_mock_settings()),
        ):
            user = _make_fake_user("user-1")
            result = await get_google_drive_auth_url(db=AsyncMock(), current_user=user)

        assert isinstance(result, ConnectorAuthUrlResponse)
        assert result.auth_url == "https://accounts.google.com/o/oauth2"

    @pytest.mark.asyncio
    async def test_raises_config_error_on_value_error(self):
        from ii_agent.integrations.connectors.router import get_google_drive_auth_url
        from ii_agent.integrations.connectors.exceptions import ConnectorConfigError

        with (
            patch.object(
                _router_module.ConnectorFactory, "create", side_effect=ValueError("bad config")
            ),
            patch.object(_router_module, "get_settings", return_value=_mock_settings()),
        ):
            user = _make_fake_user("user-1")
            with pytest.raises(ConnectorConfigError):
                await get_google_drive_auth_url(db=AsyncMock(), current_user=user)


# ---------------------------------------------------------------------------
# google_drive_callback (endpoint logic)
# ---------------------------------------------------------------------------


class TestGoogleDriveCallback:
    @pytest.mark.asyncio
    async def test_handles_callback_successfully(self):
        from ii_agent.integrations.connectors.router import google_drive_callback

        mock_connector = AsyncMock()
        mock_connector.handle_callback = AsyncMock(return_value={"access_token": "tok"})
        mock_connector.connect = AsyncMock()

        with (
            patch.object(_router_module.ConnectorFactory, "create", return_value=mock_connector),
            patch.object(_router_module, "get_settings", return_value=_mock_settings()),
        ):
            user = _make_fake_user("user-1")
            token = _create_state_token("user-1", "google_drive")
            request = ConnectorCallbackRequest(code="auth_code", state=token)

            with patch.object(
                _router_module, "_verify_state_token", return_value={"user_id": "user-1"}
            ):
                result = await google_drive_callback(
                    request=request, db=AsyncMock(), current_user=user
                )

        assert result["success"] is True


# ---------------------------------------------------------------------------
# get_github_auth_url (endpoint logic)
# ---------------------------------------------------------------------------


class TestGetGithubAuthUrl:
    @pytest.mark.asyncio
    async def test_returns_github_auth_url(self):
        from ii_agent.integrations.connectors.router import get_github_auth_url
        from ii_agent.integrations.connectors.github import GitHubConnector

        mock_connector = MagicMock(spec=GitHubConnector)
        mock_connector.get_auth_url = AsyncMock(
            return_value="https://github.com/login/oauth/authorize?..."
        )

        with (
            patch.object(_router_module.ConnectorFactory, "create", return_value=mock_connector),
            patch.object(_router_module, "get_settings", return_value=_mock_settings()),
        ):
            user = _make_fake_user("user-1")
            result = await get_github_auth_url(db=AsyncMock(), current_user=user)

        assert "github.com" in result.auth_url or result.auth_url.startswith("https://")

    @pytest.mark.asyncio
    async def test_raises_config_error_for_wrong_connector_type(self):
        from ii_agent.integrations.connectors.router import get_github_auth_url
        from ii_agent.integrations.connectors.exceptions import ConnectorConfigError

        mock_connector = MagicMock()  # not a GitHubConnector

        with (
            patch.object(_router_module.ConnectorFactory, "create", return_value=mock_connector),
            patch.object(_router_module, "get_settings", return_value=_mock_settings()),
        ):
            user = _make_fake_user("user-1")
            with pytest.raises(ConnectorConfigError):
                await get_github_auth_url(db=AsyncMock(), current_user=user)


# ---------------------------------------------------------------------------
# get_github_status
# ---------------------------------------------------------------------------


class TestGetGithubStatus:
    @pytest.mark.asyncio
    async def test_returns_status_response(self):
        from ii_agent.integrations.connectors.router import get_github_status

        status = MagicMock()
        status.is_connected = True
        status.connector_type = "github"
        status.metadata = {"login": "octocat"}
        status.access_token = "ghs_token"

        mock_connector = MagicMock()
        mock_connector.get_status = AsyncMock(return_value=status)

        with patch.object(_router_module.ConnectorFactory, "create", return_value=mock_connector):
            user = _make_fake_user("user-1")
            result = await get_github_status(db=AsyncMock(), current_user=user)

        assert isinstance(result, ConnectorStatusResponse)
        assert result.is_connected is True


# ---------------------------------------------------------------------------
# disconnect_github
# ---------------------------------------------------------------------------


class TestDisconnectGithub:
    @pytest.mark.asyncio
    async def test_disconnects_successfully(self):
        from ii_agent.integrations.connectors.router import disconnect_github

        mock_connector = AsyncMock()
        mock_connector.get_connector = AsyncMock(return_value=MagicMock())
        mock_connector.disconnect = AsyncMock()

        with patch.object(_router_module.ConnectorFactory, "create", return_value=mock_connector):
            user = _make_fake_user("user-1")
            result = await disconnect_github(db=AsyncMock(), current_user=user)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_raises_not_found_when_not_connected(self):
        from ii_agent.integrations.connectors.router import disconnect_github
        from ii_agent.integrations.connectors.exceptions import ConnectorNotFoundError

        mock_connector = AsyncMock()
        mock_connector.get_connector = AsyncMock(return_value=None)

        with patch.object(_router_module.ConnectorFactory, "create", return_value=mock_connector):
            user = _make_fake_user("user-1")
            with pytest.raises(ConnectorNotFoundError):
                await disconnect_github(db=AsyncMock(), current_user=user)


# ---------------------------------------------------------------------------
# disconnect_google_drive
# ---------------------------------------------------------------------------


class TestDisconnectGoogleDrive:
    @pytest.mark.asyncio
    async def test_disconnects_successfully(self):
        from ii_agent.integrations.connectors.router import disconnect_google_drive

        mock_connector = AsyncMock()
        mock_connector.get_connector = AsyncMock(return_value=MagicMock())
        mock_connector.disconnect = AsyncMock()

        with patch.object(_router_module.ConnectorFactory, "create", return_value=mock_connector):
            user = _make_fake_user("user-1")
            result = await disconnect_google_drive(db=AsyncMock(), current_user=user)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_raises_not_found_when_not_connected(self):
        from ii_agent.integrations.connectors.router import disconnect_google_drive
        from ii_agent.integrations.connectors.exceptions import ConnectorNotFoundError

        mock_connector = AsyncMock()
        mock_connector.get_connector = AsyncMock(return_value=None)

        with patch.object(_router_module.ConnectorFactory, "create", return_value=mock_connector):
            user = _make_fake_user("user-1")
            with pytest.raises(ConnectorNotFoundError):
                await disconnect_google_drive(db=AsyncMock(), current_user=user)


# ---------------------------------------------------------------------------
# get_github_app_config
# ---------------------------------------------------------------------------


class TestGetGithubAppConfig:
    @pytest.mark.asyncio
    async def test_returns_app_config(self):
        from ii_agent.integrations.connectors.router import get_github_app_config
        from ii_agent.integrations.connectors.github import GitHubConnector

        app_config = {
            "app_name": "ii-agent",
            "installation_url": "https://github.com/apps/ii-agent",
        }
        mock_connector = MagicMock(spec=GitHubConnector)
        mock_connector.get_app_config = AsyncMock(return_value=app_config)

        with patch.object(_router_module.ConnectorFactory, "create", return_value=mock_connector):
            result = await get_github_app_config(db=AsyncMock())

        assert result.app_name == "ii-agent"

    @pytest.mark.asyncio
    async def test_raises_config_error_for_wrong_type(self):
        from ii_agent.integrations.connectors.router import get_github_app_config
        from ii_agent.integrations.connectors.exceptions import ConnectorConfigError

        mock_connector = MagicMock()  # not a GitHubConnector

        with patch.object(_router_module.ConnectorFactory, "create", return_value=mock_connector):
            with pytest.raises(ConnectorConfigError):
                await get_github_app_config(db=AsyncMock())


# ---------------------------------------------------------------------------
# get_github_repositories
# ---------------------------------------------------------------------------


class TestGetGithubRepositories:
    @pytest.mark.asyncio
    async def test_returns_repositories_list(self):
        from ii_agent.integrations.connectors.router import get_github_repositories
        from ii_agent.integrations.connectors.github import GitHubConnector

        repos_data = [
            {
                "id": 1,
                "name": "repo-1",
                "full_name": "user/repo-1",
                "owner": {"login": "user"},
                "private": False,
                "html_url": "https://github.com/user/repo-1",
                "default_branch": "main",
                "description": "A repo",
            }
        ]
        mock_connector = MagicMock(spec=GitHubConnector)
        mock_connector.get_repositories = AsyncMock(return_value=repos_data)

        with patch.object(_router_module.ConnectorFactory, "create", return_value=mock_connector):
            user = _make_fake_user("user-1")
            result = await get_github_repositories(db=AsyncMock(), current_user=user)

        assert isinstance(result, GitHubRepositoriesResponse)
        assert len(result.repositories) == 1
        assert result.repositories[0].name == "repo-1"

    @pytest.mark.asyncio
    async def test_raises_config_error_for_wrong_type(self):
        from ii_agent.integrations.connectors.router import get_github_repositories
        from ii_agent.integrations.connectors.exceptions import ConnectorConfigError

        mock_connector = MagicMock()  # not a GitHubConnector

        with patch.object(_router_module.ConnectorFactory, "create", return_value=mock_connector):
            user = _make_fake_user("user-1")
            with pytest.raises(ConnectorConfigError):
                await get_github_repositories(db=AsyncMock(), current_user=user)

    @pytest.mark.asyncio
    async def test_empty_repos_list(self):
        from ii_agent.integrations.connectors.router import get_github_repositories
        from ii_agent.integrations.connectors.github import GitHubConnector

        mock_connector = MagicMock(spec=GitHubConnector)
        mock_connector.get_repositories = AsyncMock(return_value=[])

        with patch.object(_router_module.ConnectorFactory, "create", return_value=mock_connector):
            user = _make_fake_user("user-1")
            result = await get_github_repositories(db=AsyncMock(), current_user=user)

        assert result.repositories == []
