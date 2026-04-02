"""SQLAlchemy models for project databases domain."""

import uuid
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ii_agent.core.db.base import Base, TimestampColumn
from ii_agent.projects.databases.types import DatabaseSource

if TYPE_CHECKING:
    from ii_agent.sessions.models import Session


class ProjectDatabase(Base):
    """Database connections for projects. One-to-many with sessions."""

    __tablename__ = "project_databases"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Source identification
    source: Mapped[DatabaseSource] = mapped_column(
        String, nullable=False, default=DatabaseSource.NEONDB
    )

    # Connection details
    connection_string: Mapped[str] = mapped_column(String, nullable=False)
    host: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    database_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    branch_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Provider-specific metadata (neondb project_id, capacity info, etc.)
    db_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    session: Mapped["Session"] = relationship("Session", back_populates="databases")

    __table_args__ = (
        Index("idx_project_databases_session_id", "session_id"),
        Index("idx_project_databases_source", "source"),
        Index("idx_project_databases_is_active", "is_active"),
    )
