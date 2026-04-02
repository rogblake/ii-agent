"""Database base configuration and session management."""

import ssl
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from sqlalchemy import TIMESTAMP, func
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import DeclarativeBase
from ii_agent.core.config.settings import get_settings

# Use timezone-aware timestamps for PostgreSQL
TimestampColumn = TIMESTAMP(timezone=True)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models using SQLAlchemy 2.0 style."""
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        server_default=func.now(),
        onupdate=func.now(),
    )


def _prepare_asyncpg_url(database_url: str) -> tuple[str, dict]:
    """Parse database URL and prepare SSL connect_args for asyncpg.

    Strips SSL query params that asyncpg doesn't understand and converts
    them into a proper ssl.SSLContext in connect_args.

    Returns:
        Tuple of (cleaned_url, connect_args dict).
    """
    connect_args: dict = {}
    if "+asyncpg" not in database_url:
        return database_url, connect_args

    parsed = urlparse(database_url)
    if not parsed.query:
        return database_url, connect_args

    query_params = parse_qs(parsed.query)

    clean_params = []
    for key, values in query_params.items():
        if key not in ("sslmode", "channel_binding", "ssl"):
            for value in values:
                clean_params.append(f"{key}={value}")

    clean_query = "&".join(clean_params) if clean_params else ""
    database_url = database_url.split("?")[0]
    if clean_query:
        database_url += "?" + clean_query

    encoding_params = "client_encoding=utf8"
    if "?" in database_url:
        database_url += "&" + encoding_params
    else:
        database_url += "?" + encoding_params

    if "sslmode" in query_params:
        sslmode = query_params["sslmode"][0]
        if sslmode in ("require", "verify-ca", "verify-full"):
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connect_args["ssl"] = ssl_context

    return database_url, connect_args


# Database engine and session factory (lazy initialization)
_engine = None
_async_session_factory = None


def get_engine():
    """Get or create database engine (lazy, singleton)."""
    global _engine
    if _engine is None:
        settings = get_settings()
        if not settings.database.url:
            raise ValueError("DATABASE_URL not configured")

        database_url, connect_args = _prepare_asyncpg_url(settings.database.url)

        _engine = create_async_engine(
            database_url,
            echo=False,
            connect_args=connect_args,
            pool_size=settings.database.pool_size,
            max_overflow=settings.database.max_overflow,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_timeout=settings.database.pool_timeout,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create async session factory (lazy, singleton)."""
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_engine()
        _async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory

