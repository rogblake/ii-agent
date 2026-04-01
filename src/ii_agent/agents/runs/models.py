"""SQLAlchemy models for agent run messages.

RunTask and TaskLog have moved to ``ii_agent.tasks.models``.
This module keeps only ``AgentRunMessage`` which is agent-specific.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ii_agent.tasks.types import RunStatus
from ii_agent.core.db.base import Base, TimestampColumn

# Re-export for backward compatibility
from ii_agent.tasks.models import RunTask, TaskLog  # noqa: F401


class AgentRunMessage(Base):
    """Stores messages and run data for each agent run.

    Each record represents the output of a single agent run, including:
    - All messages exchanged during the run
    - Input/output metrics
    - Run status and metadata

    The run_id links to RunTask for run lifecycle management.
    """

    __tablename__ = "agent_run_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("run_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("run_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    model_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        String, nullable=False, default=RunStatus.RUNNING
    )
    run_input: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    messages: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    metrics: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    additional_info: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    tools: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, nullable=True)

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
        Index("ix_agent_run_messages_session_id", "session_id"),
        Index("ix_agent_run_messages_run_id", "run_id"),
        Index("ix_agent_run_messages_parent_run_id", "parent_run_id"),
        Index("ix_agent_run_messages_session_run", "session_id", "run_id"),
        Index("ix_agent_run_messages_created_at", "created_at"),
        Index("ix_agent_run_messages_status", "status"),
    )


class SessionSummary(Base):
    """Session summary storage for agent conversations.

    Stores summarised conversation data so that long sessions can be
    compacted: only the summary + messages after it need to be loaded
    into LLM context.

    One summary per session (unique index on session_id).
    """

    __tablename__ = "session_summaries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(String, nullable=False)
    topics: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    metrics: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    agent_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
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

    __table_args__ = (
        Index("ix_session_summaries_session_id", "session_id", unique=True),
        Index("ix_session_summaries_session_id_agent_run_id", "session_id", "agent_run_id"),
    )
