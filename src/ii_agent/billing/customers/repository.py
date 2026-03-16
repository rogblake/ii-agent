"""Repository layer for billing customers domain."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.customers.models import BillingCustomer

logger = logging.getLogger(__name__)


class BillingCustomerRepository:
    """Data access layer for BillingCustomer model."""

    async def get_by_user(
        self, db: AsyncSession, user_id: str, provider: str = "stripe"
    ) -> Optional[BillingCustomer]:
        """Get a billing customer by user ID and provider."""
        result = await db.execute(
            select(BillingCustomer).where(
                BillingCustomer.user_id == user_id,
                BillingCustomer.provider == provider,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_external_id(
        self, db: AsyncSession, provider: str, external_customer_id: str
    ) -> Optional[BillingCustomer]:
        """Get a billing customer by provider and external customer ID."""
        result = await db.execute(
            select(BillingCustomer).where(
                BillingCustomer.provider == provider,
                BillingCustomer.external_customer_id == external_customer_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_user_ids(
        self,
        db: AsyncSession,
        user_ids: Sequence[str],
        provider: str = "stripe",
    ) -> list[BillingCustomer]:
        """List billing customers for the provided user IDs and provider."""
        filtered_user_ids = [user_id for user_id in user_ids if user_id]
        if not filtered_user_ids:
            return []

        result = await db.execute(
            select(BillingCustomer).where(
                BillingCustomer.provider == provider,
                BillingCustomer.user_id.in_(filtered_user_ids),
            )
        )
        return list(result.scalars().all())

    async def list_by_subscription(
        self,
        db: AsyncSession,
        *,
        provider: str = "stripe",
        subscription_statuses: Iterable[str] | None = None,
        subscription_billing_cycle: str | None = None,
    ) -> list[BillingCustomer]:
        """List billing customers matching subscription filters."""
        query = select(BillingCustomer).where(BillingCustomer.provider == provider)

        if subscription_statuses is not None:
            statuses = [status for status in subscription_statuses if status]
            if not statuses:
                return []
            query = query.where(BillingCustomer.subscription_status.in_(statuses))

        if subscription_billing_cycle is not None:
            query = query.where(
                BillingCustomer.subscription_billing_cycle == subscription_billing_cycle
            )

        result = await db.execute(query)
        return list(result.scalars().all())

    async def create(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        provider: str,
        external_customer_id: str,
        subscription_plan: Optional[str] = None,
        subscription_status: Optional[str] = None,
        subscription_billing_cycle: Optional[str] = None,
        subscription_current_period_end: Optional[datetime] = None,
        customer_metadata: Optional[dict[str, Any]] = None,
    ) -> BillingCustomer:
        """Create a new billing customer record."""
        customer = BillingCustomer(
            user_id=user_id,
            provider=provider,
            external_customer_id=external_customer_id,
            subscription_plan=subscription_plan,
            subscription_status=subscription_status,
            subscription_billing_cycle=subscription_billing_cycle,
            subscription_current_period_end=subscription_current_period_end,
            customer_metadata=customer_metadata,
        )
        db.add(customer)
        await db.flush()
        return customer

    async def update_subscription(
        self,
        db: AsyncSession,
        customer: BillingCustomer,
        **fields: Any,
    ) -> None:
        """Update subscription fields on an existing billing customer.

        Accepted keyword arguments:
        - subscription_plan
        - subscription_status
        - subscription_billing_cycle
        - subscription_current_period_end
        - customer_metadata
        """
        allowed = {
            "subscription_plan",
            "subscription_status",
            "subscription_billing_cycle",
            "subscription_current_period_end",
            "customer_metadata",
        }
        for key, value in fields.items():
            if key in allowed and value is not ...:
                setattr(customer, key, value)
        await db.flush()

    async def lookup_user_id_by_customer_id(
        self, db: AsyncSession, external_customer_id: str, provider: str = "stripe"
    ) -> Optional[str]:
        """Look up user_id by external customer ID."""
        result = await db.execute(
            select(BillingCustomer.user_id).where(
                BillingCustomer.provider == provider,
                BillingCustomer.external_customer_id == external_customer_id,
            )
        )
        row = result.scalar_one_or_none()
        return row
