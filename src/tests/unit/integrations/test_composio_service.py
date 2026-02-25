import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.integrations.connectors.composio.service import ComposioService


def _config(redirect_uri: str = ""):
    return SimpleNamespace(
        composio_api_key="test-api-key",
        composio_encryption_key="unused-in-these-tests",
        composio_redirect_uri=redirect_uri,
    )


def _build_service(config=None):
    repo = AsyncMock()
    toolkit_service = AsyncMock()
    auth_config_service = AsyncMock()
    connected_account_service = AsyncMock()
    mcp_server_service = AsyncMock()

    service = ComposioService(
        repo=repo,
        config=config or _config(),
        mcp_setting_service=AsyncMock(),
        toolkit_service=toolkit_service,
        auth_config_service=auth_config_service,
        connected_account_service=connected_account_service,
        mcp_server_service=mcp_server_service,
    )
    return service, repo, toolkit_service, auth_config_service, connected_account_service, mcp_server_service


def _install_fake_config_toolkit(monkeypatch):
    module = types.ModuleType("composio_client.types.tool_router_create_session_params")

    class ConfigToolkit(dict):
        def __init__(self, toolkit):
            super().__init__(toolkit=toolkit)

    module.ConfigToolkit = ConfigToolkit

    root = types.ModuleType("composio_client")
    types_mod = types.ModuleType("composio_client.types")

    root.types = types_mod
    types_mod.tool_router_create_session_params = module

    monkeypatch.setitem(sys.modules, "composio_client", root)
    monkeypatch.setitem(sys.modules, "composio_client.types", types_mod)
    monkeypatch.setitem(
        sys.modules,
        "composio_client.types.tool_router_create_session_params",
        module,
    )


@pytest.mark.asyncio
async def test_generate_unique_profile_name_handles_collisions():
    service, repo, *_ = _build_service()

    repo.count_profiles_with_name_prefix.return_value = 2
    repo.profile_name_exists.side_effect = [True, False]

    unique_name = await service._generate_unique_profile_name(
        db=None,
        user_id="u1",
        base_name="Work Gmail",
    )

    assert unique_name == "Work Gmail (3)"


@pytest.mark.asyncio
async def test_generate_unique_profile_name_returns_base_when_no_existing():
    service, repo, *_ = _build_service()

    repo.count_profiles_with_name_prefix.return_value = 0

    unique_name = await service._generate_unique_profile_name(
        db=None,
        user_id="u1",
        base_name="Primary",
    )

    assert unique_name == "Primary"


@pytest.mark.asyncio
async def test_integrate_toolkit_uses_existing_mcp_server_branch():
    service, repo, toolkit_service, auth_config_service, connected_account_service, mcp_server_service = _build_service()

    repo.find_pending_profile.return_value = None
    repo.check_existing_auth_config.return_value = "auth-existing"
    repo.get_user_mcp_server_id.return_value = "mcp-existing"

    toolkit_service.get_toolkit_by_slug.return_value = {"slug": "gmail", "name": "Gmail"}
    auth_config_service.create_auth_config.return_value = SimpleNamespace(id="auth-1")
    connected_account_service.create_connected_account.return_value = SimpleNamespace(
        id="conn-1",
        status="ACTIVE",
        redirect_url="https://oauth.example.com",
    )

    service.get_user_composio_mcp_configs = AsyncMock(
        return_value={"composio": {"url": "https://mcp.existing"}}
    )
    service.create_profile = AsyncMock(return_value=SimpleNamespace(id="profile-1"))

    mcp_server_service.update_mcp_server.return_value = SimpleNamespace(id="mcp-existing")

    response = await service.integrate_toolkit(
        db=None,
        toolkit_slug="gmail",
        user_id="user-1",
        profile_name="My Gmail",
    )

    assert response.success is True
    assert response.profile_id == "profile-1"
    assert response.connection_status == "ACTIVE"

    mcp_server_service.update_mcp_server.assert_awaited_once_with(
        mcp_server_id="mcp-existing",
        auth_config_ids=["auth-1"],
        toolkit_slug="gmail",
    )
    mcp_server_service.create_mcp_server.assert_not_called()


@pytest.mark.asyncio
async def test_integrate_toolkit_uses_new_mcp_server_branch():
    service, repo, toolkit_service, auth_config_service, connected_account_service, mcp_server_service = _build_service()

    repo.find_pending_profile.return_value = None
    repo.check_existing_auth_config.return_value = None
    repo.get_user_mcp_server_id.return_value = None

    toolkit_service.get_toolkit_by_slug.return_value = {"slug": "gmail", "name": "Gmail"}
    auth_config_service.create_auth_config.return_value = SimpleNamespace(id="auth-1")
    connected_account_service.create_connected_account.return_value = SimpleNamespace(
        id="conn-1",
        status="PENDING",
        redirect_url=None,
    )
    service.create_profile = AsyncMock(return_value=SimpleNamespace(id="profile-2"))

    mcp_server_service.create_mcp_server.return_value = (
        SimpleNamespace(id="mcp-new"),
        "https://mcp.new",
    )

    response = await service.integrate_toolkit(
        db=None,
        toolkit_slug="gmail",
        user_id="user-1",
        profile_name="My Gmail",
        redirect_url="https://frontend.example.com/callback",
    )

    assert response.success is False
    assert response.profile_id == "profile-2"
    assert response.connection_status == "PENDING"
    assert response.redirect_url == "https://frontend.example.com/callback"

    mcp_server_service.create_mcp_server.assert_awaited_once()
    mcp_server_service.update_mcp_server.assert_not_called()


@pytest.mark.asyncio
async def test_delete_pending_profile_cleans_connected_account_and_profile():
    service, repo, *_rest, connected_account_service, _mcp_server_service = _build_service()

    repo.find_pending_profile.return_value = SimpleNamespace(
        id="profile-1",
        connected_account_id="ca-1",
    )

    deleted = await service._delete_pending_profile(
        db=None,
        user_id="user-1",
        toolkit_slug="gmail",
    )

    assert deleted is True
    connected_account_service.delete_connected_account.assert_awaited_once_with("ca-1")
    repo.delete_by_id.assert_awaited_once_with(None, "profile-1")


@pytest.mark.asyncio
async def test_complete_oauth_updates_pending_profile_to_enable():
    service, repo, *_ = _build_service()

    repo.find_profile_by_connected_account.return_value = SimpleNamespace(id="profile-1")
    repo.update_status.return_value = True

    result = await service.complete_oauth(
        db=None,
        user_id="user-1",
        app_name="gmail",
        connected_account_id="ca-1",
    )

    assert result is True
    repo.update_status.assert_awaited_once_with(None, "profile-1", "user-1", "enable")


@pytest.mark.asyncio
async def test_complete_oauth_returns_false_when_profile_missing():
    service, repo, *_ = _build_service()

    repo.find_profile_by_connected_account.return_value = None

    result = await service.complete_oauth(
        db=None,
        user_id="user-1",
        app_name="gmail",
        connected_account_id="ca-missing",
    )

    assert result is False
    repo.update_status.assert_not_called()


@pytest.mark.asyncio
async def test_update_profile_tools_syncs_allowed_tools_to_mcp_server(monkeypatch):
    _install_fake_config_toolkit(monkeypatch)

    service, repo, *_rest, mcp_server_service = _build_service()

    target_profile = SimpleNamespace(
        id="profile-1",
        mcp_server_id="mcp-1",
        toolkit_slug="gmail",
        auth_config_id="auth-gmail",
        enabled_tools=["GMAIL_OLD"],
    )
    sibling_profile = SimpleNamespace(
        id="profile-2",
        mcp_server_id="mcp-1",
        toolkit_slug="slack",
        auth_config_id="auth-slack",
        enabled_tools=["SLACK_LIST_CHANNELS"],
    )

    repo.get_by_id_and_user.return_value = target_profile
    repo.update_enabled_tools.return_value = True
    repo.get_profiles_by_mcp_server.return_value = [target_profile, sibling_profile]

    mcp_server_service.get_mcp_server.return_value = SimpleNamespace(id="mcp-1")
    mcp_server_service._call_mcp_update = MagicMock()

    updated = await service.update_profile_tools(
        db=None,
        profile_id="profile-1",
        user_id="user-1",
        enabled_tools=["GMAIL_SEND_EMAIL"],
    )

    assert updated is True
    repo.update_enabled_tools.assert_awaited_once_with(
        None,
        "profile-1",
        ["GMAIL_SEND_EMAIL"],
    )

    args = mcp_server_service._call_mcp_update.call_args.args
    assert args[0] == "mcp-1"

    toolkits = args[1]
    allowed_tools = set(args[2])

    assert {item["toolkit"] for item in toolkits} == {"gmail", "slack"}
    assert {item["auth_config"] for item in toolkits} == {"auth-gmail", "auth-slack"}
    assert allowed_tools == {"GMAIL_SEND_EMAIL", "SLACK_LIST_CHANNELS"}


@pytest.mark.asyncio
async def test_update_profile_tools_returns_false_when_profile_missing():
    service, repo, *_ = _build_service()

    repo.get_by_id_and_user.return_value = None

    updated = await service.update_profile_tools(
        db=None,
        profile_id="missing",
        user_id="user-1",
        enabled_tools=["A"],
    )

    assert updated is False
    repo.update_enabled_tools.assert_not_called()


def test_resolve_callback_url_prefers_config_value():
    service, *_ = _build_service(config=_config("https://config.example.com/callback"))

    request = SimpleNamespace(
        headers={"referer": "https://frontend.example.com/page"},
        url=SimpleNamespace(scheme="https", netloc="api.example.com"),
    )

    callback = service.resolve_callback_url(request)

    assert callback == "https://config.example.com/callback"


def test_resolve_callback_url_uses_referer_or_request_origin():
    service, *_ = _build_service(config=_config(""))

    with_referer = SimpleNamespace(
        headers={"referer": "https://frontend.example.com/path"},
        url=SimpleNamespace(scheme="https", netloc="api.example.com"),
    )
    no_referer = SimpleNamespace(
        headers={},
        url=SimpleNamespace(scheme="https", netloc="api.example.com"),
    )

    assert (
        service.resolve_callback_url(with_referer)
        == "https://frontend.example.com/auth/oauth/composio/callback"
    )
    assert (
        service.resolve_callback_url(no_referer)
        == "https://api.example.com/auth/oauth/composio/callback"
    )
