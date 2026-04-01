from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

import ii_agent.projects.databases.service as database_service_module
from ii_agent.projects.databases.exceptions import ProjectDatabaseError
from ii_agent.projects.databases.service import (
    DatabaseService,
    _fetch_table_names_sync,
    _fetch_table_records_sync,
)


def _service(settings_factory, db_repo=None):
    return DatabaseService(
        project_repo=AsyncMock(),
        db_repo=db_repo or AsyncMock(),
        config=settings_factory(),
    )


def test_parse_connection_string_edge_cases(settings_factory):
    service = _service(settings_factory)

    host, db_name, role = service._parse_connection_string(
        "postgresql://alice:secret@db.example.com:5432/appdb"
    )
    assert host == "db.example.com"
    assert db_name == "appdb"
    assert role == "alice"

    host2, db_name2, role2 = service._parse_connection_string("postgresql://bob@db.example.com")
    assert host2 == "db.example.com"
    assert db_name2 is None
    assert role2 == "bob"

    host3, db_name3, role3 = service._parse_connection_string(None)  # type: ignore[arg-type]
    assert host3 is None
    assert db_name3 is None
    assert role3 is None


def test_fetch_table_names_sync_maps_sqlalchemy_error(monkeypatch):
    fake_engine = SimpleNamespace(dispose=MagicMock())

    monkeypatch.setattr(
        database_service_module, "create_engine", lambda *args, **kwargs: fake_engine
    )

    def _raise(_engine):
        raise SQLAlchemyError("failed inspector")

    monkeypatch.setattr(database_service_module, "inspect", _raise)

    with pytest.raises(ProjectDatabaseError, match="failed inspector"):
        _fetch_table_names_sync("postgresql://db")

    fake_engine.dispose.assert_called_once()


def test_fetch_table_records_sync_maps_table_load_error(monkeypatch):
    fake_engine = SimpleNamespace(dispose=MagicMock())

    monkeypatch.setattr(
        database_service_module, "create_engine", lambda *args, **kwargs: fake_engine
    )

    def _raise_table(*args, **kwargs):
        raise SQLAlchemyError("table load failed")

    monkeypatch.setattr(database_service_module, "Table", _raise_table)

    with pytest.raises(ProjectDatabaseError, match="table load failed"):
        _fetch_table_records_sync(
            "postgresql://db",
            table_name="users",
            limit=10,
            offset=0,
        )

    fake_engine.dispose.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_database_from_url_updates_existing_or_creates_new(settings_factory):
    db_repo = AsyncMock()
    service = _service(settings_factory, db_repo=db_repo)

    existing = SimpleNamespace(
        source=None,
        connection_string=None,
        host=None,
        database_name=None,
        role_name=None,
    )

    db_repo.get_active_by_session_id.side_effect = [existing, None]

    async def _update(db, record):
        return record

    db_repo.update.side_effect = _update
    db_repo.create.return_value = SimpleNamespace(id="db-new")

    updated = await service.upsert_database_from_url(
        db=None,
        session_id="session-1",
        connection_string="postgresql://user1:pw@host-1:5432/db_one",
        source="user",
    )

    assert updated is existing
    assert updated.source == "user"
    assert updated.host == "host-1"
    assert updated.database_name == "db_one"
    assert updated.role_name == "user1"

    created = await service.upsert_database_from_url(
        db=None,
        session_id="session-2",
        connection_string="postgresql://user2:pw@host-2:5432/db_two",
        source="supabase",
    )

    assert created.id == "db-new"
    db_repo.create.assert_awaited_once_with(
        None,
        session_id="session-2",
        source="supabase",
        connection_string="postgresql://user2:pw@host-2:5432/db_two",
        host="host-2",
        database_name="db_two",
        role_name="user2",
    )
