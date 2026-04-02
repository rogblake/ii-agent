"""Database manager and connection infrastructure.

This module provides:
- Migration utilities (run_migrations)
- Session context managers (get_db, get_db_session_local)

All engine/session-factory creation is delegated to core.db.base
(lazy, singleton) so importing this module has NO side effects.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import exc
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import II_AGENT_DIR
from ii_agent.core.db.base import get_session_factory
from ii_agent.core.logger import logger


def run_migrations():
    """Run database migrations using Alembic."""
    try:
        from alembic import command
        from alembic.config import Config

        project_root = II_AGENT_DIR.parent.parent
        alembic_cfg = Config(project_root / "alembic.ini")
        migrations_path = project_root / "migrations"
        alembic_cfg.set_main_option("script_location", str(migrations_path))

        command.upgrade(alembic_cfg, "head")

    except Exception as e:
        logger.error(f"Error running migrations: {e}")
        raise


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session as a context manager.

    Yields:
        A database session that will be automatically rolled back on error.
    """
    async with get_session_factory()() as db:
        try:
            yield db
        except exc.SQLAlchemyError as db_exc:
            await db.rollback()
            logger.error(f"Database session rollback due to exception, {db_exc}")
            raise


@asynccontextmanager
async def get_db_session_local() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session as a context manager with auto-commit.

    Yields:
        A database session that will be automatically committed or rolled back.
    """
    async with get_session_factory()() as db:
        try:
            yield db
            await db.commit()
        except exc.SQLAlchemyError as db_exc:
            await db.rollback()
            logger.error(
                f"Exception during local session, rolling back, error: {db_exc}"
            )
            raise
