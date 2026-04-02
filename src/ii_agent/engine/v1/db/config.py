from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Type, TypeVar, get_args, get_origin

from pydantic import ValidationError
from sqlalchemy import BigInteger, Boolean, Index, String, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from ii_agent.core.db.base import Base, TimestampColumn


class ConfigKey(str, Enum):
    AGENT_V1_VERSION_TOGGLE = "agent_v1_version_toggle"


T = TypeVar("T")


class ApplicationConfig(Base):
    """Application-wide configuration storage.

    Stores key-value configuration pairs with support for:
    - JSON values for complex configuration
    - Secret flagging for sensitive data
    - Optimistic locking via version column
    """

    __tablename__ = "application_configs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[ConfigKey] = mapped_column(String, nullable=False, unique=True)
    value: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __mapper_args__ = {"version_id_col": version}

    __table_args__ = (Index("ix_application_configs_is_secret", "is_secret"),)

    @classmethod
    async def get_by_key(
        cls,
        key: ConfigKey,
        *,
        db: Optional[AsyncSession] = None,
    ) -> Optional["ApplicationConfig"]:
        """Get a config record by key.

        Args:
            key: The config key to look up.
            db: Optional database session. If not provided, creates a new one.

        Returns:
            ApplicationConfig record if found, None otherwise.
        """

        async def _query(session: AsyncSession) -> Optional["ApplicationConfig"]:
            result = await session.execute(select(cls).where(cls.key == key))
            return result.scalar_one_or_none()

        if db is not None:
            return await _query(db)

        from ii_agent.core.db.manager import get_db_session_local

        async with get_db_session_local() as session:
            return await _query(session)

    @classmethod
    async def get_value(
        cls,
        key: ConfigKey,
        value_type: Type[T],
        *,
        default: Optional[T] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[T]:
        """Get a config value by key with type casting.

        JSONB already returns correct Python types (bool, str, int, dict, list).
        This method only adds Pydantic model validation on top.

        Args:
            key: The config key to look up.
            value_type: Expected type (bool, str, dict, list, or Pydantic model).
            default: Default value if config not found.
            db: Optional database session.

        Examples:
            await get_value(ConfigKey.TOGGLE, bool, default=False)
            await get_value(ConfigKey.FLAGS, MyModel, default=MyModel())
            await get_value(ConfigKey.ITEMS, List[MyModel], default=[])
        """
        config = await cls.get_by_key(key, db=db)
        if config is None or config.value is None:
            return default

        value = config.value

        try:
            # List[PydanticModel]
            origin = get_origin(value_type)
            if origin is list and isinstance(value, list):
                args = get_args(value_type)
                if args and hasattr(args[0], "model_validate"):
                    return [args[0].model_validate(item) for item in value]  # type: ignore
                return value  # type: ignore

            # Single Pydantic model
            if hasattr(value_type, "model_validate"):
                if isinstance(value, dict):
                    return value_type.model_validate(value)  # type: ignore

            # Primitives (bool, str, int, dict, list) - validate type matches
            if isinstance(value, value_type):  # type: ignore
                return value  # type: ignore
            return default

        except (ValueError, TypeError, ValidationError):
            return default
