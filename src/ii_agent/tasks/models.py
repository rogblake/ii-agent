"""SQLAlchemy models for run tasks and task logs."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import BigInteger, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ii_agent.tasks.types import RunStatus, TaskType
from ii_agent.core.db.base import Base, TimestampColumn


class RunTask(Base):
    """Unified run lifecycle tracker for all execution types.

    Every user-initiated action (agent query, chat message, media generation)
    creates exactly one RunTask. The task.id IS the run_id used by the Redis
    cancel system.

    Columns:
        session_id: The session this task belongs to.
        task_type: Discriminator for the kind of work (agent_run, chat_run, media_generation).
        status: Current run status (pending -> running -> completed/failed/cancelled).
        error_message: Error details when status is FAILED.
        data: Arbitrary JSONB metadata attached to the task.
        version: Optimistic locking counter for concurrent updates.
    """

    __tablename__ = "run_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key, also used as run_id for the Redis cancel system",
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        comment="The session this task belongs to",
    )
    task_type: Mapped[TaskType] = mapped_column(
        String(32),
        nullable=False,
        comment="Discriminator: agent_run, chat_run, or media_generation",
    )
    status: Mapped[RunStatus] = mapped_column(
        String(32),
        nullable=False,
        default=RunStatus.RUNNING,
        comment="Current run status: pending, running, completed, paused, aborting, cancelled, failed",
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
        comment="Error details when status is failed",
    )
    data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Arbitrary metadata attached to the task",
    )

    # Optimistic locking
    version: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
        comment="Optimistic locking counter for concurrent updates",
    )

    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        comment="Timestamp when the task was created",
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="Timestamp of the last update",
    )

    __mapper_args__ = {"version_id_col": version}

    __table_args__ = (
        Index("ix_run_tasks_session_id", "session_id"),
        Index("ix_run_tasks_status", "status"),
        Index("ix_run_tasks_session_status", "session_id", "status"),
        Index("ix_run_tasks_created_at", "created_at"),
        Index("ix_run_tasks_task_type", "task_type"),
        # Enforce at most one active task per (session, task_type)
        Index(
            "uq_run_tasks_session_type_active",
            "session_id",
            "task_type",
            unique=True,
            postgresql_where=text(RunStatus.active_status_sql()),
        ),
    )

    def is_active(self) -> bool:
        """Check if task is in an active (non-terminal) state."""
        return self.status in RunStatus.active_states()

    def is_running(self) -> bool:
        """Check if task is running."""
        return self.status == RunStatus.RUNNING


class TaskLog(Base):
    """Append-only audit trail of run_task status transitions.

    Every status change on a RunTask inserts a row here. Never updated or deleted.
    """

    __tablename__ = "task_logs"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="Auto-increment primary key",
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("run_tasks.id", ondelete="CASCADE"),
        nullable=False,
        comment="FK to the run_task this log entry belongs to",
    )
    status: Mapped[RunStatus] = mapped_column(
        String(32),
        nullable=False,
        comment="The status the task transitioned to",
    )
    data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Optional snapshot of metadata at the time of transition",
    )
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        comment="Timestamp when this status transition occurred",
    )

    __table_args__ = (
        Index("ix_task_logs_task_id", "task_id"),
        Index("ix_task_logs_created_at", "created_at"),
        Index("ix_task_logs_task_created", "task_id", "created_at"),
    )
