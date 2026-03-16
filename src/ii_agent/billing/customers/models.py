"""SQLAlchemy models for billing customers domain."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ii_agent.core.db.base import Base, TimestampColumn

if TYPE_CHECKING:
    from ii_agent.auth.users.models import User


class BillingCustomer(Base):
    """Billing customer record linking a user to an external payment provider."""

    __tablename__ = "billing_customers"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="stripe",
    )
    external_customer_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    subscription_plan: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subscription_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subscription_billing_cycle: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    subscription_current_period_end: Mapped[Optional[datetime]] = mapped_column(
        TimestampColumn, nullable=True
    )
    customer_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="billing_customers")

    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_billing_customers_user_provider"),
        UniqueConstraint("provider", "external_customer_id", name="uq_billing_customers_provider_external"),
        Index("idx_billing_customers_user", "user_id"),
    )
