"""SQLAlchemy models for chat runs."""

from datetime import datetime, timezone
from typing import Optional
import uuid
from enum import Enum
from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UUID
from ii_agent.core.db.base import Base, TimestampColumn


class ChatRunStatus(str, Enum):
    """Run status for chat runs."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class ChatRun(Base):
    """Tracks the lifecycle of a chat run.

    Each chat message exchange creates a run that tracks:
    - Status transitions (running -> completed/failed/aborted)
    - Timing information
    """

    __tablename__ = "chat_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=lambda: uuid.uuid4()
    )
    session_id: Mapped[str] = mapped_column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    user_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=ChatRunStatus.RUNNING.value
    )
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Optimistic locking
    version: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __mapper_args__ = {"version_id_col": version}

    __table_args__ = (
        Index("ix_chat_runs_session_id", "session_id"),
        Index("ix_chat_runs_status", "status"),
        Index("ix_chat_runs_session_status", "session_id", "status"),
    )
