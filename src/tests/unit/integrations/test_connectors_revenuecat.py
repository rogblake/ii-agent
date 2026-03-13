"""Unit tests for ii_agent.integrations.connectors.revenuecat."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.integrations.connectors.revenuecat import RevenueCatConnector


def _settings(
    *,
    revenuecat_client_id: str = "client-id",
    revenuecat_client_secret: str = "client-secret",
    revenuecat_redirect_uri: str = "https://app.local/auth/oauth/revenuecat/callback",
):
    oauth = SimpleNamespace(
        revenuecat_client_id=revenuecat_client_id,
        revenuecat_client_secret=revenuecat_client_secret,
        revenuecat_redirect_uri=revenuecat_redirect_uri,
    )
    oauth.has_revenuecat_oauth = lambda: bool(oauth.revenuecat_client_id)
    return SimpleNamespace(oauth=oauth)


def _make_async_client() -> AsyncMock:
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    return client


def _make_response(payload: dict[str, str], *, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = "{}"
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    return response


@pytest.mark.asyncio
async def test_exchange_token_keeps_client_secret_for_pkce_confidential_client():
    connector = RevenueCatConnector(db_session=MagicMock())
    client = _make_async_client()
    client.post = AsyncMock(return_value=_make_response({"access_token": "token"}))

    with (
        patch(
            "ii_agent.integrations.connectors.revenuecat.get_settings",
            return_value=_settings(),
        ),
        patch(
            "ii_agent.integrations.connectors.revenuecat.httpx.AsyncClient",
            return_value=client,
        ),
    ):
        await connector._exchange_token(
            data={
                "grant_type": "authorization_code",
                "code": "auth-code",
                "redirect_uri": "https://app.local/callback",
                "code_verifier": "verifier-123",
            }
        )

    payload = client.post.await_args.kwargs["data"]
    assert payload["client_id"] == "client-id"
    assert payload["client_secret"] == "client-secret"
    assert payload["code_verifier"] == "verifier-123"


@pytest.mark.asyncio
async def test_exchange_token_supports_public_pkce_clients_without_secret():
    connector = RevenueCatConnector(db_session=MagicMock())
    client = _make_async_client()
    client.post = AsyncMock(return_value=_make_response({"access_token": "token"}))

    with (
        patch(
            "ii_agent.integrations.connectors.revenuecat.get_settings",
            return_value=_settings(revenuecat_client_secret=""),
        ),
        patch(
            "ii_agent.integrations.connectors.revenuecat.httpx.AsyncClient",
            return_value=client,
        ),
    ):
        await connector._exchange_token(
            data={
                "grant_type": "authorization_code",
                "code": "auth-code",
                "redirect_uri": "https://app.local/callback",
                "code_verifier": "verifier-123",
            }
        )

    payload = client.post.await_args.kwargs["data"]
    assert payload["client_id"] == "client-id"
    assert "client_secret" not in payload


@pytest.mark.asyncio
async def test_handle_callback_falls_back_to_default_redirect_uri():
    connector = RevenueCatConnector(db_session=MagicMock())

    with (
        patch(
            "ii_agent.integrations.connectors.revenuecat.get_settings",
            return_value=_settings(
                revenuecat_redirect_uri="https://app.local/default-callback"
            ),
        ),
        patch.object(
            connector,
            "_exchange_token",
            AsyncMock(return_value={"access_token": "token", "scope": ""}),
        ) as exchange_token,
        patch.object(connector, "list_projects", AsyncMock(return_value=[])),
    ):
        await connector.handle_callback(
            "auth-code",
            "state",
            redirect_uri=None,
            code_verifier="verifier-123",
        )

    exchange_payload = exchange_token.await_args.kwargs["data"]
    assert exchange_payload["redirect_uri"] == "https://app.local/default-callback"
