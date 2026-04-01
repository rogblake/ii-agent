from contextlib import asynccontextmanager

import pytest
from sqlalchemy import exc

from ii_agent.core.db import base as manager


class _FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_get_db_session_local_rolls_back_on_sqlalchemy_error(monkeypatch):
    session = _FakeSession()

    @asynccontextmanager
    async def _session_cm():
        yield session

    monkeypatch.setattr(manager, "get_session_factory", lambda: _session_cm)

    with pytest.raises(exc.SQLAlchemyError):
        async with manager.get_db_session_local():
            raise exc.SQLAlchemyError("boom")

    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_get_db_session_local_commits_on_success(monkeypatch):
    session = _FakeSession()

    @asynccontextmanager
    async def _session_cm():
        yield session

    monkeypatch.setattr(manager, "get_session_factory", lambda: _session_cm)

    async with manager.get_db_session_local():
        pass

    assert session.commits == 1
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_get_db_session_local_rolls_back_on_error(monkeypatch):
    session = _FakeSession()

    @asynccontextmanager
    async def _session_cm():
        yield session

    monkeypatch.setattr(manager, "get_session_factory", lambda: _session_cm)

    with pytest.raises(exc.SQLAlchemyError):
        async with manager.get_db_session_local():
            raise exc.SQLAlchemyError("boom")

    assert session.rollbacks == 1
