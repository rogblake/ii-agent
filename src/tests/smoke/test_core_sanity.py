from contextlib import asynccontextmanager
from types import SimpleNamespace
import importlib

import pytest
from sqlalchemy import exc

from ii_agent.auth.jwt_handler import JWTHandler
from ii_agent.core.db import base as db_manager

pytestmark = pytest.mark.smoke


@pytest.mark.asyncio
async def test_db_session_manager_commit_and_rollback_paths(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.committed = 0
            self.rolled_back = 0

        async def commit(self):
            self.committed += 1

        async def rollback(self):
            self.rolled_back += 1

    session = FakeSession()

    @asynccontextmanager
    async def _session_cm():
        yield session

    monkeypatch.setattr(db_manager, "get_session_factory", lambda: _session_cm)

    async with db_manager.get_db_session_local():
        pass

    assert session.committed == 1

    with pytest.raises(exc.SQLAlchemyError):
        async with db_manager.get_db_session_local():
            raise exc.SQLAlchemyError("boom")

    assert session.rolled_back == 1


def test_auth_token_issue_and_verify(monkeypatch):
    jwt_module = importlib.import_module("ii_agent.auth.jwt_handler")
    monkeypatch.setattr(
        jwt_module,
        "get_settings",
        lambda: SimpleNamespace(
            jwt_secret_key="smoke-secret",
            access_token_expire_minutes=10,
            refresh_token_expire_days=7,
        ),
    )

    handler = JWTHandler()
    token = handler.create_access_token("user-1", "user@example.com")

    payload = handler.verify_access_token(token)

    assert payload["user_id"] == "user-1"
    assert handler.verify_access_token("invalid-token") is None
