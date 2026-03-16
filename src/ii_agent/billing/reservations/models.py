"""SQLAlchemy model for prepaid credit reservations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ii_agent.core.db.base import Base, TimestampColumn


def _uuid4_str() -> str:
    return str(uuid.uuid4())


class CreditReservation(Base):
    """Durable hold for prepaid billable work."""

    __tablename__ = "credit_reservations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid4_str)
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    source_domain: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    billing_kind: Mapped[str] = mapped_column(String, nullable=False)
    quote_strategy: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    model_id: Mapped[str | None] = mapped_column(String, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    reserve_ledger_entry_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("credit_ledger.id"),
        nullable=True,
    )
    release_ledger_entry_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("credit_ledger.id"),
        nullable=True,
    )
    shortfall_ledger_entry_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("credit_ledger.id"),
        nullable=True,
    )
    usage_record_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("usage_records.id"),
        nullable=True,
    )
    reserved_credits: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
    )
    reserved_bonus_credits: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
    )
    actual_credits: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    actual_bonus_credits: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6),
        nullable=True,
    )
    released_credits: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6),
        nullable=True,
    )
    released_bonus_credits: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6),
        nullable=True,
    )
    quoted_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
    )
    max_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
    )
    actual_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    reservation_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(TimestampColumn, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        Index("idx_credit_reservations_user_created", "user_id", "created_at"),
        Index("idx_credit_reservations_source", "source_domain", "source_id"),
        Index("idx_credit_reservations_status_expires", "status", "expires_at"),
        Index(
            "uq_credit_reservations_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=idempotency_key.isnot(None),
        ),
    )

