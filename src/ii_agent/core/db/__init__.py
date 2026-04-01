"""Database infrastructure.

Usage::

    from ii_agent.core.db import Base, TimestampColumn, AsyncSession
    from ii_agent.core.db import get_db_session_local, get_engine, shutdown_engine
    from ii_agent.core.db import BaseRepository
"""

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.base import (
    Base,
    BaseRepository,
    TimestampColumn,
    get_db,
    get_db_session_local,
    get_engine,
    get_session_factory,
    run_migrations,
    shutdown_engine,
)

__all__ = [
    # ORM
    "Base",
    "TimestampColumn",
    "AsyncSession",
    # Repository
    "BaseRepository",
    # Engine & session
    "get_engine",
    "get_session_factory",
    "get_db_session_local",
    "get_db",
    "shutdown_engine",
    # Migrations
    "run_migrations",
]
