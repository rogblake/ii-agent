"""SQLAlchemy models for billing domain.

BillingTransaction: Stripe webhook audit log -- records every processed
Stripe event for idempotency and auditing.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ii_agent.core.db.base import Base

if TYPE_CHECKING:
    from ii_agent.users.models import User


class BillingTransaction(Base):
    """Stripe webhook audit log.

    Inherits ``id``, ``created_at``, ``updated_at`` from :class:`Base`.
    """

    __tablename__ = "billing_transactions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    stripe_event_id: Mapped[str] = mapped_column(String, unique=True)
    stripe_object_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    stripe_invoice_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stripe_payment_intent_id: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    amount: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    plan_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    billing_cycle: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    credits: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="billing_transactions")

    __table_args__ = (
        Index("idx_billing_transactions_user_id", "user_id"),
        Index("idx_billing_transactions_subscription", "stripe_subscription_id"),
    )
