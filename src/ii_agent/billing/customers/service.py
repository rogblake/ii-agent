"""Service layer for billing customer management."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.customers.models import BillingCustomer
from ii_agent.billing.customers.repository import BillingCustomerRepository

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class EffectiveBillingProfile:
    """Effective customer/subscription state resolved from billing_customers."""

    external_customer_id: str | None
    subscription_plan: str | None
    subscription_status: str | None
    subscription_billing_cycle: str | None
    subscription_current_period_end: datetime | None


class BillingCustomerService:
    """Business logic for billing customer operations."""

    def __init__(self, *, customer_repo: BillingCustomerRepository) -> None:
        self._customer_repo = customer_repo

    async def get_by_user(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        provider: str = "stripe",
    ) -> Optional[BillingCustomer]:
        """Get an existing billing customer for a user/provider."""
        return await self._customer_repo.get_by_user(db, user_id, provider)

    async def list_by_user_ids(
        self,
        db: AsyncSession,
        user_ids: Sequence[str],
        *,
        provider: str = "stripe",
    ) -> dict[str, BillingCustomer]:
        """Return billing customers keyed by user_id for the given provider."""
        customers = await self._customer_repo.list_by_user_ids(
            db,
            user_ids,
            provider,
        )
        return {customer.user_id: customer for customer in customers}

    async def list_by_subscription(
        self,
        db: AsyncSession,
        *,
        provider: str = "stripe",
        subscription_statuses: Iterable[str] | None = None,
        subscription_billing_cycle: str | None = None,
    ) -> list[BillingCustomer]:
        """List billing customers matching subscription filters."""
        return await self._customer_repo.list_by_subscription(
            db,
            provider=provider,
            subscription_statuses=subscription_statuses,
            subscription_billing_cycle=subscription_billing_cycle,
        )

    async def get_or_create(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        provider: str = "stripe",
        external_customer_id: str,
        **sub_fields: Any,
    ) -> BillingCustomer:
        """Get an existing billing customer or create a new one."""
        existing = await self._customer_repo.get_by_user(db, user_id, provider)
        if existing:
            # Update external_customer_id if it changed
            if existing.external_customer_id != external_customer_id:
                existing.external_customer_id = external_customer_id
                await db.flush()
            return existing

        return await self._customer_repo.create(
            db,
            user_id=user_id,
            provider=provider,
            external_customer_id=external_customer_id,
            **sub_fields,
        )

    async def update_subscription(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        provider: str = "stripe",
        subscription_plan: Optional[str] = ...,  # type: ignore[assignment]
        subscription_status: Optional[str] = ...,  # type: ignore[assignment]
        subscription_billing_cycle: Optional[str] = ...,  # type: ignore[assignment]
        subscription_current_period_end: Optional[datetime] = ...,  # type: ignore[assignment]
    ) -> Optional[BillingCustomer]:
        """Update subscription fields on an existing billing customer."""
        customer = await self._customer_repo.get_by_user(db, user_id, provider)
        if not customer:
            logger.warning(
                "BillingCustomer not found for user %s (provider=%s); skipping update",
                user_id,
                provider,
            )
            return None

        await self._customer_repo.update_subscription(
            db,
            customer,
            subscription_plan=subscription_plan,
            subscription_status=subscription_status,
            subscription_billing_cycle=subscription_billing_cycle,
            subscription_current_period_end=subscription_current_period_end,
        )
        return customer

    async def lookup_user_id(
        self, db: AsyncSession, external_customer_id: str, provider: str = "stripe"
    ) -> Optional[str]:
        """Look up user_id by external customer ID."""
        return await self._customer_repo.lookup_user_id_by_customer_id(
            db, external_customer_id, provider
        )

    def resolve_effective_profile(
        self,
        *,
        customer: BillingCustomer | None = None,
        **_kwargs: Any,
    ) -> EffectiveBillingProfile:
        """Resolve subscription state from ``billing_customers`` only."""
        return EffectiveBillingProfile(
            external_customer_id=(
                customer.external_customer_id if customer is not None else None
            ),
            subscription_plan=(
                customer.subscription_plan if customer is not None else None
            ),
            subscription_status=(
                customer.subscription_status if customer is not None else None
            ),
            subscription_billing_cycle=(
                customer.subscription_billing_cycle
                if customer is not None
                else None
            ),
            subscription_current_period_end=(
                customer.subscription_current_period_end
                if customer is not None
                else None
            ),
        )

    async def get_effective_profile(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        provider: str = "stripe",
        **_kwargs: Any,
    ) -> EffectiveBillingProfile:
        """Load billing customer state and resolve the effective profile."""
        customer = await self.get_by_user(
            db,
            user_id,
            provider=provider,
        )
        return self.resolve_effective_profile(customer=customer)
