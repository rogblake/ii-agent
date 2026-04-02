from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ii_agent.projects import router as project_router
from ii_agent.projects.databases.service import DatabaseService
from ii_agent.projects.databases.types import DatabaseSource


def _database_service(settings_factory, *, project_repo=None, db_repo=None) -> DatabaseService:
    return DatabaseService(
        project_repo=project_repo or AsyncMock(),
        db_repo=db_repo or AsyncMock(),
        config=settings_factory(),
    )


@pytest.mark.asyncio
async def test_get_project_db_payload_prefers_active_project_database(settings_factory):
    project_repo = AsyncMock()
    db_repo = AsyncMock()
    service = _database_service(
        settings_factory,
        project_repo=project_repo,
        db_repo=db_repo,
    )

    project_repo.get_by_id_and_user.return_value = SimpleNamespace(
        session_id="session-1",
        database_json={"connection_string": "postgresql://stale-db"},
    )
    db_repo.get_active_by_session_id.return_value = SimpleNamespace(
        id=uuid4(),
        session_id=uuid4(),
        source=DatabaseSource.NEONDB,
        connection_string="postgresql://fresh-db",
        host="db.example.com",
        database_name="app_db",
        role_name="app_user",
        branch_name="main",
        is_active=True,
        db_metadata={"project_id": "neon-project-1"},
    )

    payload = await service.get_project_db_payload(None, uuid4(), uuid4())

    assert payload is not None
    assert payload["connection_string"] == "postgresql://fresh-db"
    assert payload["project_id"] == "neon-project-1"
    assert payload["source"] == "neondb"


@pytest.mark.asyncio
async def test_get_project_db_connection_falls_back_to_project_database_json(settings_factory):
    project_repo = AsyncMock()
    db_repo = AsyncMock()
    service = _database_service(
        settings_factory,
        project_repo=project_repo,
        db_repo=db_repo,
    )

    project_repo.get_by_id_and_user.return_value = SimpleNamespace(
        session_id=uuid4(),
        database_json={"url": "postgresql://legacy-db"},
    )
    db_repo.get_active_by_session_id.return_value = None

    result = await service.get_project_db_connection(None, uuid4(), uuid4())

    assert result == "postgresql://legacy-db"


@pytest.mark.asyncio
async def test_project_router_hydrates_database_from_project_database():
    session_id = uuid4()
    user_id = uuid4()
    project_id = uuid4()

    project_service = AsyncMock()
    database_service = AsyncMock()

    project_service.get_session_project.return_value = SimpleNamespace(
        id=project_id,
        user_id=user_id,
        session_id=session_id,
        name="Demo Project",
        description=None,
        status="active",
        current_build_status="idle",
        framework="nextjs-shadcn",
        project_path="/workspace/demo",
        production_url=None,
        database_json=None,
        storage_json=None,
        secrets_json=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    database_service.get_session_db_payload.return_value = {
        "connection_string": "postgresql://project-db",
        "source": "neondb",
    }

    result = await project_router.get_session_project(
        session_id,
        SimpleNamespace(id=user_id),
        project_service,
        database_service,
        None,
    )

    project_service.get_session_project.assert_awaited_once_with(
        None,
        session_id=session_id,
        user_id=user_id,
    )
    database_service.get_session_db_payload.assert_awaited_once_with(None, session_id)
    assert result.database == {
        "connection_string": "postgresql://project-db",
        "source": "neondb",
    }
