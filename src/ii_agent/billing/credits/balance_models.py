"""SQLAlchemy model for materialized credit balances."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ii_agent.core.db.base import Base, TimestampColumn


class BillingStatus(str, enum.Enum):
    """Account-level billing health."""

    OK = "ok"
    RECONCILIATION_REQUIRED = "reconciliation_required"


def _uuid4_str() -> str:
    return str(uuid.uuid4())


class CreditBalanceRecord(Base):
    """Materialized credit balance per user.

    One row per user. Updated atomically on every credit mutation.
    ``credit_ledger`` remains the append-only audit trail.
    """

    __tablename__ = "credit_balances"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=_uuid4_str,
    )
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    credits: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
    )
    bonus_credits: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
    )
    billing_status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=BillingStatus.OK.value,
    )
    billing_status_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    billing_status_updated_at: Mapped[datetime | None] = mapped_column(
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
    )

    __table_args__ = (
        CheckConstraint("credits >= 0", name="ck_credit_balances_credits_floor"),
        CheckConstraint(
            "bonus_credits >= 0", name="ck_credit_balances_bonus_credits_floor"
        ),
    )
