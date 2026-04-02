"""SQLAlchemy models for agents domain."""

from datetime import datetime, timezone
from typing import Optional, List
import uuid
from enum import Enum
from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UUID
from ii_agent.core.db.base import Base, TimestampColumn


class RunStatus(str, Enum):
    """Unified run status for agent runs.

    This is the single source of truth for run statuses across the application.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PAUSED = "paused"
    ABORTING = "aborting"
    ABORTED = "aborted"  # Kept for backwards compatibility
    FAILED = "failed"
    ERROR = "error"
    SYSTEM_INTERRUPTED = "system_interrupted"

    @classmethod
    def from_string(cls, status: str) -> "RunStatus":
        """Convert a string to RunStatus, handling case-insensitivity."""
        status_lower = status.lower()
        for member in cls:
            if member.value == status_lower:
                return member
        # Default to running if unknown
        return cls.RUNNING

    @staticmethod
    def runable_states() -> List["RunStatus"]:
        return [RunStatus.RUNNING, RunStatus.PAUSED, RunStatus.ABORTING]


class AgentRunTask(Base):
    """Tracks the lifecycle of an agent run.

    Each run creates a task that tracks:
    - Status transitions (running -> completed/failed/cancelled/paused)
    - Associated messages via AgentRunMessage
    - Timing information

    Session info (user_id, agent_type, etc.) is available via the sessions table.
    """

    __tablename__ = "agent_run_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=lambda: uuid.uuid4()
    )
    session_id: Mapped[str] = mapped_column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    # Original user message ID that triggered this run
    user_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID, nullable=True)
    # Current status of the run
    status: Mapped[str] = mapped_column(String, nullable=False, default=RunStatus.RUNNING.value)
    # Error message if status is FAILED or ERROR
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

    # Optimistic locking configuration
    __mapper_args__ = {"version_id_col": version}

    __table_args__ = (
        Index("ix_agent_run_tasks_session_id", "session_id"),
        Index("ix_agent_run_tasks_status", "status"),
        Index("ix_agent_run_tasks_session_status", "session_id", "status"),
        Index("ix_agent_run_tasks_created_at", "created_at"),
    )

    def is_running(self) -> bool:
        """Check if task is running."""
        return bool(self.status == RunStatus.RUNNING)
