"""SQLAlchemy model for durable billing usage facts."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UUID

from ii_agent.core.db.base import Base, TimestampColumn


class BillingUsageFact(Base):
    """One durable billable invocation fact tied to a reservation."""

    __tablename__ = "billing_usage_facts"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    reservation_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("credit_reservations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID, nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID, nullable=True)
    billing_kind: Mapped[str] = mapped_column(String, nullable=False)
    event_kind: Mapped[str] = mapped_column(String, nullable=False)
    app_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    request_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    model_id: Mapped[str | None] = mapped_column(String, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String, nullable=True)
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
    charged_credits: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String, default="captured", nullable=False)
    attempt_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(
        TimestampColumn,
        nullable=True,
    )
    last_enqueued_at: Mapped[datetime | None] = mapped_column(
        TimestampColumn,
        nullable=True,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        TimestampColumn,
        nullable=True,
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        TimestampColumn,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_billing_usage_facts_status_created", "status", "created_at"),
        Index(
            "idx_billing_usage_facts_dispatchable",
            "status",
            "processing_started_at",
            "created_at",
        ),
        Index("idx_billing_usage_facts_session_created", "session_id", "created_at"),
        Index("idx_billing_usage_facts_user_created", "user_id", "created_at"),
        Index("idx_billing_usage_facts_run_created", "run_id", "created_at"),
    )
