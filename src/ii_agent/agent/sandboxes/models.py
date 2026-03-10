"""SQLAlchemy models for sandboxes domain."""

from datetime import datetime, timezone
import uuid
from typing import Any, Optional

from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB, UUID

from ii_agent.core.db.base import Base, TimestampColumn
from ii_agent.agent.sandboxes.schemas import SandboxStatus


class Sandbox(Base):
    """Database model for sandboxes."""

    __tablename__ = "sandboxes"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    provider: Mapped[str] = mapped_column(String, default="e2b")
    provider_sandbox_id: Mapped[str] = mapped_column(String, nullable=True)
    provider_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    session_id: Mapped[uuid.UUID] = mapped_column(String, nullable=False)
    status: Mapped[SandboxStatus] = mapped_column(String, default=SandboxStatus.NOT_INITIALIZED)

    # Optimistic locking version
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn, default=lambda: datetime.now(timezone.utc)
    )
    expired_at: Mapped[Optional[datetime]] = mapped_column(
        TimestampColumn, nullable=True, default=None
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("session_id", name="uq_sandboxes_session_id"),
        Index("idx_sandboxes_status", "status"),
        Index("idx_sandboxes_provider_sandbox_id", "provider", "provider_sandbox_id"),
    )

    __mapper_args__ = {
        "version_id_col": version,
    }
