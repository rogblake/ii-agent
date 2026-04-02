from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from ii_agent.integrations.connectors.service import ConnectorService


class FakeConnectorRepo:
    def __init__(self):
        self.connector = None

    async def get_by_user_and_type(self, db, user_id, connector_type):
        return self.connector

    async def get_by_token_and_type(self, db, token, connector_type):
        if self.connector and self.connector.access_token == token:
            return self.connector
        return None


class FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_save_mcp_token_creates_or_updates_connector(settings_factory):
    repo = FakeConnectorRepo()
    service = ConnectorService(connector_repo=repo, config=settings_factory())

    db = FakeDB()
    await service.save_mcp_token(
        db,
        access_token="token-1",
        user_id="u1",
        user_email="u1@example.com",
        expires_in=3600,
    )

    assert len(db.added) == 1
    created = db.added[0]
    assert created.access_token == "token-1"

    repo.connector = created
    await service.save_mcp_token(
        db,
        access_token="token-2",
        user_id="u1",
        user_email="u1@example.com",
        expires_in=1800,
    )

    assert repo.connector.access_token == "token-2"


@pytest.mark.asyncio
async def test_get_user_by_mcp_token_handles_expired_token(settings_factory):
    repo = FakeConnectorRepo()
    repo.connector = SimpleNamespace(
        user_id="u1",
        access_token="token-1",
        token_expiry=datetime.now(timezone.utc) - timedelta(seconds=1),
        connector_metadata={"user_email": "u1@example.com"},
    )

    service = ConnectorService(connector_repo=repo, config=settings_factory())

    assert await service.get_user_by_mcp_token(None, token="token-1") is None


@pytest.mark.asyncio
async def test_get_user_by_mcp_token_returns_defaults(settings_factory):
    repo = FakeConnectorRepo()
    repo.connector = SimpleNamespace(
        user_id="u1",
        access_token="token-1",
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
        connector_metadata=None,
    )

    service = ConnectorService(connector_repo=repo, config=settings_factory())

    result = await service.get_user_by_mcp_token(None, token="token-1")

    assert result == {"user_id": "u1", "user_email": ""}
