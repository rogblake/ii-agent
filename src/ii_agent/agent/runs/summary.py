from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Type, TypeVar, get_args, get_origin

from pydantic import ValidationError
from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, String, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from ii_agent.core.db.base import Base, TimestampColumn


class AgentSummary(Base):
    """Session summary storage for agent conversations.

    Stores summarized conversation data for sessions including:
    - Summary text capturing the key points of the conversation
    - Topics extracted from the session (stored as JSONB)
    - Metrics about the session (token counts, duration, etc.)
    - Reference to the session and agent run that generated the summary

    Attributes:
        id: Primary key, auto-incrementing BigInteger.
        content: The summarized text content of the session.
        topics: JSON array of topics/themes extracted from the conversation.
        metrics: JSON object containing session metrics (tokens, duration, etc.).
        session_id: Foreign key reference to the session being summarized.
        agent_run_id: Foreign key reference to the agent run that created this summary.
        version: Optimistic locking version for concurrent update handling.
        created_at: Timestamp when the content was created.
        updated_at: Timestamp when the content was last updated.

    Indexes:
        - Unique index on session_id for fast lookups and ensuring one summary per session.
        - Composite index on (session_id, agent_run_id) for efficient queries by both fields.
    """

    __tablename__ = "agent_summaries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(String, nullable=False)
    topics: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    metrics: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
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
        Index("ix_agent_summaries_session_id", "session_id", unique=True),
        Index("ix_agent_summaries_session_id_agent_run_id", "session_id", "agent_run_id"),
    )
