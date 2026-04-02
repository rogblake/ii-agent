"""Repository layer for billing domain - data access only."""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.models import BillingTransaction


class BillingTransactionRepository:
    """Data access layer for BillingTransaction model."""

    async def get_by_event_id(self, db: AsyncSession, event_id: str) -> Optional[BillingTransaction]:
        """Get a billing transaction by its Stripe event ID."""
        result = await db.execute(
            select(BillingTransaction).where(
                BillingTransaction.stripe_event_id == event_id
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        stripe_event_id: str,
        **values: Any,
    ) -> BillingTransaction:
        """Create a new billing transaction record."""
        transaction = BillingTransaction(
            user_id=user_id,
            stripe_event_id=stripe_event_id,
            **values,
        )
        db.add(transaction)
        await db.flush()
        return transaction
