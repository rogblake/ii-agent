from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest_asyncio
from sqlalchemy import ARRAY, UUID as SA_UUID, event
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles

# Ensure model imports that depend on this path remain writable in tests.
os.environ.setdefault("COMPOSIO_CACHE_DIR", "/tmp/.composio")

# Import all phase-2 model modules so mapper relationships are fully registered.
import ii_agent.auth.models  # noqa: F401
import ii_agent.auth.users.models  # noqa: F401
import ii_agent.billing.models  # noqa: F401
import ii_agent.billing.usage.models  # noqa: F401
import ii_agent.chat.models  # noqa: F401
import ii_agent.content.media.models  # noqa: F401
import ii_agent.content.skills.models  # noqa: F401
import ii_agent.content.slides.models  # noqa: F401
import ii_agent.content.storybook.models  # noqa: F401
import ii_agent.agent.runs.models  # noqa: F401
import ii_agent.agent.sandboxes.models  # noqa: F401
import ii_agent.files.models  # noqa: F401
import ii_agent.integrations.connectors.models  # noqa: F401
import ii_agent.mobile.apple.models  # noqa: F401
import ii_agent.projects.databases.models  # noqa: F401
import ii_agent.projects.deployments.models  # noqa: F401
import ii_agent.projects.models  # noqa: F401
import ii_agent.projects.subdomains.models  # noqa: F401
import ii_agent.agent.events.models  # noqa: F401
import ii_agent.sessions.models  # noqa: F401
import ii_agent.sessions.wishlist.models  # noqa: F401
import ii_agent.settings.llm.models  # noqa: F401
import ii_agent.settings.mcp.models  # noqa: F401
from ii_agent.auth.users.models import User
from ii_agent.core.db.base import Base
from ii_agent.projects.models import Project
from ii_agent.sessions.models import Session


@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(PG_UUID, "sqlite")
def _compile_pg_uuid(_type, _compiler, **_kw) -> str:
    return "TEXT"


@compiles(SA_UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "TEXT"


@pytest_asyncio.fixture(scope="session")
async def repository_engine(tmp_path_factory) -> AsyncIterator[AsyncEngine]:
    db_path = Path(tmp_path_factory.mktemp("repositories-db")) / "repositories.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(repository_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with repository_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            if transaction.is_active:
                await transaction.rollback()


@pytest_asyncio.fixture
async def user_factory(
    db_session: AsyncSession,
) -> Callable[..., Any]:
    async def _create_user(**overrides: Any) -> User:
        values = {
            "id": str(uuid.uuid4()),
            "email": f"user-{uuid.uuid4().hex[:10]}@example.com",
            "credits": 100.0,
            "bonus_credits": 0.0,
        }
        values.update(overrides)
        user = User(**values)
        db_session.add(user)
        await db_session.flush()
        return user

    return _create_user


@pytest_asyncio.fixture
async def session_factory(
    db_session: AsyncSession,
    user_factory,
) -> Callable[..., Any]:
    async def _create_session(**overrides: Any) -> Session:
        values: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "name": "Session",
            "status": "active",
            "api_version": "v1",
        }
        values.update(overrides)
        if "user_id" not in values:
            user = await user_factory()
            values["user_id"] = user.id

        session = Session(**values)
        db_session.add(session)
        await db_session.flush()
        return session

    return _create_session


@pytest_asyncio.fixture
async def project_factory(
    db_session: AsyncSession,
    user_factory,
) -> Callable[..., Any]:
    async def _create_project(**overrides: Any) -> Project:
        values: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "name": "Project",
        }
        values.update(overrides)
        if "user_id" not in values:
            user = await user_factory()
            values["user_id"] = user.id

        project = Project(**values)
        db_session.add(project)
        await db_session.flush()
        return project

    return _create_project
