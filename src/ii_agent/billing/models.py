"""SQLAlchemy models for billing domain.

Models migrated from core/db/models.py:
- BillingTransaction
"""

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Numeric, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
import uuid

from ii_agent.core.db.base import Base, TimestampColumn

# Forward references for relationships
if TYPE_CHECKING:
    from ii_agent.auth.users.models import User


class BillingTransaction(Base):
    """Database model for Stripe billing transactions."""

    __tablename__ = "billing_transactions"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE")
    )
    stripe_event_id: Mapped[str] = mapped_column(String, unique=True)
    stripe_object_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stripe_invoice_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stripe_payment_intent_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    amount: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    plan_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    billing_cycle: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    credits: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
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
    user: Mapped["User"] = relationship("User", back_populates="billing_transactions")

    # Indexes
    __table_args__ = (
        Index("idx_billing_transactions_user_id", "user_id"),
        Index("idx_billing_transactions_subscription", "stripe_subscription_id"),
    )
