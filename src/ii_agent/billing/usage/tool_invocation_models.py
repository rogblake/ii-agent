"""SQLAlchemy models for tool invocation telemetry."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import BigInteger, Boolean, Identity, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UUID

from ii_agent.core.db.base import Base, TimestampColumn


class ToolInvocation(Base):
    """Append-only telemetry rows for tool executions."""

    __tablename__ = "tool_invocations"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID, nullable=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    billing_context: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    subject_kind: Mapped[str] = mapped_column(String, nullable=False, default="session")
    subject_id: Mapped[str | None] = mapped_column(String, nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID, nullable=True)
    provider_tool_call_id: Mapped[str | None] = mapped_column(String, nullable=True)
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    tool_namespace: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(TimestampColumn, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TimestampColumn, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    input_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    is_error: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    credits_charged: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_tool_invocations_run", "run_id", "created_at"),
        Index("idx_tool_invocations_billing_context", "billing_context", "created_at"),
        Index("idx_tool_invocations_subject", "subject_kind", "subject_id", "created_at"),
        Index("idx_tool_invocations_tool", "tool_name", "created_at"),
    )

    @property
    def session_id(self) -> str | None:
        if self.subject_kind == "session":
            return self.subject_id
        return None
