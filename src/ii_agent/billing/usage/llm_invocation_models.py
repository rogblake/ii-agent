"""SQLAlchemy models for LLM invocation telemetry."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import BigInteger, Boolean, Identity, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UUID

from ii_agent.core.db.base import Base, TimestampColumn


class LLMInvocation(Base):
    """Append-only telemetry rows for individual LLM calls."""

    __tablename__ = "llm_invocations"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID, nullable=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    billing_context: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    subject_kind: Mapped[str] = mapped_column(String, nullable=False, default="session")
    subject_id: Mapped[str | None] = mapped_column(String, nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID, nullable=True)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    request_kind: Mapped[str] = mapped_column(String, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )
    cache_read_tokens: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )
    cache_write_tokens: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )
    reasoning_tokens: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )
    latency_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    credits_charged: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6),
        nullable=True,
    )
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_llm_invocations_run", "run_id", "created_at"),
        Index("idx_llm_invocations_billing_context", "billing_context", "created_at"),
        Index("idx_llm_invocations_subject", "subject_kind", "subject_id", "created_at"),
        Index("idx_llm_invocations_model", "model", "created_at"),
        Index("idx_llm_invocations_user", "user_id", "created_at"),
    )

    @property
    def session_id(self) -> str | None:
        if self.subject_kind == "session":
            return self.subject_id
        return None
