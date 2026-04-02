"""ORM models for the credits domain (per ADR-004).

Two-table design:
- ``credit_balances``    — materialized current balance per user
- ``credit_transactions`` — immutable append-only ledger (single source of truth)

Invariant:
    SUM(amount WHERE credit_type='regular')  == credit_balances.credits
    SUM(amount WHERE credit_type='bonus')    == credit_balances.bonus_credits
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
import uuid

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ii_agent.core.db.base import Base
from ii_agent.credits.types import CreditType, TransactionType


# ---------------------------------------------------------------------------
# CreditBalance — materialized balance per user
# ---------------------------------------------------------------------------


class CreditBalance(Base):
    """Materialized credit balance per user.

    One row per user. Created on signup. Updated atomically alongside
    every ``credit_transactions`` INSERT inside a SAVEPOINT.

    ``version`` column enables optimistic locking to prevent lost-update
    races when concurrent deductions happen.
    """

    __tablename__ = "credit_balances"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Numeric(18, 6) for precise money arithmetic (6 decimal places)
    credits: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, server_default="0")
    bonus_credits: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, server_default="0"
    )

    # Optimistic lock version — incremented on every balance mutation
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}

    # Account health
    billing_status: Mapped[str] = mapped_column(String, nullable=False, default="ok")
    billing_status_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    billing_status_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def total(self) -> Decimal:
        """Total available credits (bonus + regular)."""
        return self.credits + self.bonus_credits


# ---------------------------------------------------------------------------
# CreditTransaction — immutable append-only ledger
# ---------------------------------------------------------------------------


class CreditTransaction(Base):
    """Immutable append-only ledger of all credit movements.

    Every credit change — whether from Stripe top-ups, LLM usage, tool costs,
    admin grants, or refunds — is recorded here as the **single source of truth**.

    Positive ``amount`` = credits added (top-up).
    Negative ``amount`` = credits removed (deduction).

    Invariant:
        SUM(amount WHERE credit_type='regular')  == credit_balances.credits
        SUM(amount WHERE credit_type='bonus')    == credit_balances.bonus_credits
    """

    __tablename__ = "credit_transactions"

    # ── Who ──
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # ── What ──
    transaction_type: Mapped[TransactionType] = mapped_column(String(30), nullable=False)
    credit_type: Mapped[CreditType] = mapped_column(
        String(10), default=CreditType.REGULAR, nullable=False
    )

    # Numeric(18, 6) for precise money — NOT Float
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    # Snapshot of the affected pool's balance AFTER this transaction
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    # ── Context (nullable, depends on transaction type) ──
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    model_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # For Stripe-originated top-ups: link back to audit log
    billing_transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("billing_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Flexible metadata (token counts, pricing breakdown, tool name, etc.)
    data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "data", JSONB, server_default=text("'{}'::jsonb"), nullable=True
    )

    __table_args__ = (
        Index("idx_credit_tx_user", "user_id", "created_at"),
        Index(
            "idx_credit_tx_session",
            "session_id",
            "created_at",
            postgresql_where=text("session_id IS NOT NULL"),
        ),
        Index("idx_credit_tx_type", "user_id", "transaction_type", "created_at"),
    )
