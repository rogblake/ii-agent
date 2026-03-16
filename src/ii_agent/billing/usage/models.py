"""Data models for LLM metrics tracking.

This module contains:
- SQLAlchemy models: SessionMetrics
- Pydantic models: TokenUsage

Note: The Event model has been moved to ii_agent.agent.events.models.
Note: ModelPricing lives in ii_agent.billing.credits.pricing (single source of truth).
"""

from decimal import Decimal
from typing import Dict, Optional
from datetime import datetime, timezone
import uuid

from pydantic import BaseModel, Field, model_validator, ConfigDict
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import BigInteger, ForeignKey, Identity, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

from ii_agent.core.db.base import Base, TimestampColumn


# ==================== SQLAlchemy Models ====================


class SessionMetrics(Base):
    """Database model for session-level credits tracking."""

    __tablename__ = "session_metrics"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        unique=True,
    )

    # Credits tracking
    credits: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"), nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    session = relationship("Session", backref="metrics", uselist=False)

    # Add indexes for efficient queries
    __table_args__ = (
        Index("idx_session_metrics_session_id", "session_id"),
        Index("idx_session_metrics_updated_at", "updated_at"),
    )


class UsageRecord(Base):
    """Normalized billable-event records linked to credit ledger entries."""

    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    ledger_entry_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("credit_ledger.id"),
        nullable=True,
    )
    source_domain: Mapped[str] = mapped_column(String, nullable=False)
    billing_kind: Mapped[str] = mapped_column(String, nullable=False)
    app_kind: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tool_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    model_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
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
    latency_ms: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    credits_charged: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    usage_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_usage_records_user_created", "user_id", "created_at"),
        Index("idx_usage_records_session", "session_id", "created_at"),
        Index("idx_usage_records_source", "source_domain", "created_at"),
        Index("idx_usage_records_billing_kind", "billing_kind", "created_at"),
        Index("idx_usage_records_model", "model_id", "created_at"),
        Index(
            "uq_usage_records_ledger_entry_id",
            "ledger_entry_id",
            unique=True,
            postgresql_where=ledger_entry_id.isnot(None),
        ),
    )


# ==================== Pydantic Models ====================


class TokenUsage(BaseModel):
    """Token usage statistics for an LLM call."""

    model_config = ConfigDict(extra="allow")

    prompt_tokens: int = Field(default=0, description="Number of tokens in the prompt")
    completion_tokens: int = Field(
        default=0, description="Number of tokens in the completion"
    )
    cache_read_tokens: int = Field(
        default=0, description="Number of tokens read from cache"
    )
    cache_write_tokens: int = Field(
        default=0, description="Number of tokens written to cache"
    )
    reasoning_tokens: int = Field(
        default=0, description="Number of reasoning tokens consumed"
    )

    # Additional response metadata
    model_name: Optional[str] = Field(
        default=None, description="Name of the model used"
    )
    response_time_ms: Optional[float] = Field(
        default=None, description="Response time in milliseconds"
    )

    total_tokens: Optional[int] = Field(
        default=None, description="Total tokens used (prompt + completion)"
    )

    input_token_details: Optional[Dict] = Field(default=None)

    output_token_details: Optional[Dict] = Field(default=None)

    @model_validator(mode="after")
    def calculate_total_tokens(self) -> "TokenUsage":
        """Calculate total_tokens if not provided."""
        cache_creation_tokens = (self.model_extra or {}).get("cache_creation_tokens")
        if self.cache_write_tokens == 0 and cache_creation_tokens is not None:
            self.cache_write_tokens = int(cache_creation_tokens)

        if self.reasoning_tokens == 0:
            if self.output_token_details:
                self.reasoning_tokens = int(
                    self.output_token_details.get("reasoning_tokens", 0) or 0
                )
            else:
                self.reasoning_tokens = int(
                    (self.model_extra or {}).get("reasoning_tokens", 0) or 0
                )

        if self.total_tokens is None:
            self.total_tokens = (
                self.prompt_tokens
                + self.completion_tokens
                + self.cache_write_tokens
                + self.cache_read_tokens
            )
        return self

    @classmethod
    def from_raw_metrics(
        cls, raw_metrics: dict, model_name: Optional[str] = None
    ) -> "TokenUsage":
        return cls(
            prompt_tokens=raw_metrics.get("input_tokens", 0),
            completion_tokens=raw_metrics.get("output_tokens", 0),
            cache_read_tokens=raw_metrics.get("cache_read_input_tokens", 0),
            cache_write_tokens=raw_metrics.get("cache_creation_input_tokens", 0),
            reasoning_tokens=raw_metrics.get("reasoning_tokens", 0),
            model_name=model_name or raw_metrics.get("model_name"),
            response_time_ms=raw_metrics.get("response_time_ms"),
        )
