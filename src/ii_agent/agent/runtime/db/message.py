from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB, UUID
from ii_agent.agent.agents.models import RunStatus
from ii_agent.core.db.base import Base, TimestampColumn


class AgentRunMessage(Base):
    """Stores messages and run data for each agent run.

    Each record represents the output of a single agent run, including:
    - All messages exchanged during the run
    - Input/output metrics
    - Run status and metadata

    The run_id links to AgentRunTask for run lifecycle management.
    """

    __tablename__ = "agent_run_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    # Foreign key to AgentRunTask for run lifecycle tracking
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("agent_run_tasks.id", ondelete="CASCADE"), nullable=False
    )
    # Parent run ID for sub-agent runs (links to the parent agent's run)
    parent_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID, nullable=True)
    model_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        String, nullable=False, default=RunStatus.RUNNING.value
    )
    # Run input data (the original user input)
    run_input: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    # All messages from the run (user, assistant, tool calls, tool results)
    messages: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    # Metrics (tokens, duration, etc.)
    metrics: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    # Additional info (agent_id, content, reasoning, etc.)
    additional_info: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    # Tool executions (for paused runs with pending tool confirmations)
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

    # Optimistic locking configuration
    __mapper_args__ = {"version_id_col": version}

    __table_args__ = (
        Index("ix_agent_run_messages_session_id", "session_id"),
        Index("ix_agent_run_messages_run_id", "run_id"),
        Index("ix_agent_run_messages_parent_run_id", "parent_run_id"),
        Index("ix_agent_run_messages_session_run", "session_id", "run_id"),
        Index("ix_agent_run_messages_created_at", "created_at"),
        Index("ix_agent_run_messages_status", "status"),
    )
