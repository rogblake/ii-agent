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

    async def claim_event(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        stripe_event_id: str,
    ) -> bool:
        """Atomically claim a Stripe event for processing.

        Uses ``INSERT … ON CONFLICT DO NOTHING`` on the unique
        ``stripe_event_id`` column.  Returns ``True`` if this call won
        the insert (caller should proceed with mutations) or ``False``
        if another transaction already claimed the event.
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = (
            pg_insert(BillingTransaction)
            .values(
                user_id=user_id,
                stripe_event_id=stripe_event_id,
                status="processing",
            )
            .on_conflict_do_nothing(index_elements=["stripe_event_id"])
            .returning(BillingTransaction.id)
        )
        result = await db.execute(stmt)
        await db.flush()
        return result.first() is not None

    async def update_by_event_id(
        self,
        db: AsyncSession,
        *,
        stripe_event_id: str,
        **values: Any,
    ) -> None:
        """Update a previously claimed transaction with final values."""
        existing = await self.get_by_event_id(db, stripe_event_id)
        if existing:
            for key, val in values.items():
                setattr(existing, key, val)
            await db.flush()

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
