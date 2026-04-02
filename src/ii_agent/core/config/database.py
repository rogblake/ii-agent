"""Database configuration settings."""

from typing import Optional
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration settings.

    Environment variables:
        DB_URL or DATABASE_URL: PostgreSQL connection URL

    Example:
        DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname
    """

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: Optional[str] = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/ii_agent",
        validation_alias=AliasChoices("DB_URL", "DATABASE_URL", "database_url"),
        description="Database connection URL (PostgreSQL with asyncpg driver)",
    )

    pool_size: int = Field(
        default=10,
        description="Connection pool size",
        ge=1,
    )

    max_overflow: int = Field(
        default=20,
        description="Maximum overflow connections",
        ge=0,
    )

    pool_timeout: int = Field(
        default=30,
        description="Connection pool timeout in seconds",
        ge=1,
    )

    echo: bool = Field(
        default=False,
        description="Echo SQL statements (for debugging)",
    )
