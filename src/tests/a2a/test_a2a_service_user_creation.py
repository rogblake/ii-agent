"""Tests for service user bootstrap logic in the A2A agent."""

import os
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ii_agent.integrations.a2a.as_server import IIAgentA2AServer
from ii_agent.core.config.settings import get_settings
from ii_agent.auth.users.models import User


TEST_SCHEMA_NAME = os.getenv("II_AGENT_TEST_SCHEMA", "test_ii_agent_a2a")


@pytest.fixture(scope="session")
def _postgres_test_schema():
    """Create a dedicated PostgreSQL schema for A2A tests."""

    settings = get_settings()
    sync_url = settings.sync_database_url
    async_url = settings.database.url or sync_url
    if async_url.startswith("postgresql://"):
        async_url = async_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_engine(
        sync_url,
        isolation_level="AUTOCOMMIT",
        future=True,
    )

    try:
        with engine.connect() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA_NAME} CASCADE"))
            connection.execute(text(f"CREATE SCHEMA {TEST_SCHEMA_NAME}"))
    except OperationalError as exc:  # pragma: no cover - depends on external DB
        engine.dispose()
        pytest.skip(f"PostgreSQL test database unavailable: {exc}")

    try:
        yield {"async_url": async_url, "schema": TEST_SCHEMA_NAME}
    finally:
        with engine.connect() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA_NAME} CASCADE"))
        engine.dispose()


@pytest_asyncio.fixture
async def in_memory_session_factory(monkeypatch, _postgres_test_schema):
    """Provide a PostgreSQL-backed session factory and patch get_db_session_local."""
    async_url = _postgres_test_schema["async_url"]
    schema = _postgres_test_schema["schema"]

    engine = create_async_engine(
        async_url,
        connect_args={
            "server_settings": {"search_path": f"{schema},public"},
        },
        future=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.drop, checkfirst=True)
        await conn.run_sync(User.__table__.create)

    session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )

    @asynccontextmanager
    async def fake_get_db_session_local():
        async with session_factory() as session:
            yield session
            await session.commit()

    monkeypatch.setattr(
        "ii_agent.integrations.a2a.as_server.get_db_session_local",
        fake_get_db_session_local,
    )

    try:
        yield session_factory
    finally:
        await engine.dispose()


def make_agent(**config_overrides) -> IIAgentA2AServer:
    agent = IIAgentA2AServer()
    config = {
        "a2a_default_session_user_email": None,
        "default_user_credits": 0.0,
    }
    config.update(config_overrides)
    agent._config = SimpleNamespace(**config)
    return agent


@pytest.mark.asyncio
async def test_creates_user_with_synthesized_email(in_memory_session_factory):
    agent = make_agent()
    await agent._ensure_session_user_exists("worker-1")

    async with in_memory_session_factory() as session:
        result = await session.execute(select(User).where(User.id == "worker-1"))
        created = result.scalar_one()

    assert created.email == "worker-1@a2a.local"
    assert created.role == "service"


@pytest.mark.asyncio
async def test_formats_template_email_with_user_id(in_memory_session_factory):
    agent = make_agent(
        a2a_default_session_user_email="{user_id}@svc.example",
        default_user_credits=13.5,
    )
    await agent._ensure_session_user_exists("service-bot")

    async with in_memory_session_factory() as session:
        result = await session.execute(select(User).where(User.id == "service-bot"))
        created = result.scalar_one()

    assert created.email == "service-bot@svc.example"
    assert created.credits == 13.5


@pytest.mark.asyncio
async def test_falls_back_when_template_email_conflicts(in_memory_session_factory):
    async with in_memory_session_factory() as session:
        session.add(
            User(
                id="existing-user",
                email="duplicate@svc.example",
                role="service",
                is_active=True,
                credits=0.0,
                bonus_credits=0.0,
            )
        )
        await session.commit()

    agent = make_agent(a2a_default_session_user_email="duplicate@svc.example")
    await agent._ensure_session_user_exists("new-user")

    async with in_memory_session_factory() as session:
        result = await session.execute(select(User).where(User.id == "new-user"))
        created = result.scalar_one()

    assert created.email == "new-user@a2a.local"
