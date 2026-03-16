"""SQLAlchemy model for credit ledger entries."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ii_agent.core.db.base import Base, TimestampColumn


class LedgerEntryType(str, enum.Enum):
    """Types of credit ledger entries."""

    INITIAL_BALANCE = "initial_balance"
    DEDUCTION = "deduction"
    GRANT = "grant"
    BONUS_GRANT = "bonus_grant"
    PLAN_CHANGE = "plan_change"
    RESERVATION_HOLD = "reservation_hold"
    RESERVATION_RELEASE = "reservation_release"


class CreditLedgerEntry(Base):
    """Append-only ledger of credit balance changes."""

    __tablename__ = "credit_ledger"

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
    entry_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    source_domain: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )
    delta_credits: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
    )
    delta_bonus_credits: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
    )
    balance_after_credits: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 6), nullable=True,
    )
    balance_after_bonus_credits: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 6), nullable=True,
    )
    entry_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_credit_ledger_user_created", "user_id", created_at.desc()),
        Index("idx_credit_ledger_source", "source_domain", "source_id"),
        Index("idx_credit_ledger_entry_type", "entry_type", created_at.desc()),
        Index(
            "uq_credit_ledger_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=idempotency_key.isnot(None),
        ),
    )
