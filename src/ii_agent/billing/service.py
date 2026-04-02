"""Billing service for Stripe checkout and portal sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import stripe
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.stripe_config import StripeConfig
from ii_agent.billing.exceptions import (
    BillingConfigurationError,
    BillingServiceError,
    BillingUnsupportedPlanError,
)
from ii_agent.auth.users.repository import UserRepository


@dataclass(slots=True)
class CheckoutSessionParams:
    """Parameters required to create a checkout session."""

    plan_id: str
    billing_cycle: str
    user_id: str
    return_url: str | None


class BillingService:
    """Service responsible for creating Stripe checkout and portal sessions."""

    def __init__(
        self,
        *,
        stripe_config: StripeConfig,
        user_repo: UserRepository,
    ) -> None:
        self._stripe_config = stripe_config
        self._user_repo = user_repo

    async def create_checkout_session(
        self, db: AsyncSession, params: CheckoutSessionParams
    ) -> stripe.checkout.Session:
        if params.plan_id == "free":
            raise BillingUnsupportedPlanError("Free plan does not require checkout")

        self._stripe_config.ensure_api_key()

        price_id = self._stripe_config.get_price_id(params.plan_id, params.billing_cycle)
        success_url, cancel_url = self._stripe_config.resolve_return_urls(params.return_url)

        metadata = {
            "plan_id": params.plan_id,
            "billing_cycle": params.billing_cycle,
            "user_id": params.user_id,
        }

        customer_kwargs: dict[str, Any] = {}
        user = await self._user_repo.get_by_id(db, params.user_id)
        if user and user.stripe_customer_id:
            customer_kwargs["customer"] = user.stripe_customer_id

        session = await run_in_threadpool(
            stripe.checkout.Session.create,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=params.user_id,
            metadata=metadata,
            subscription_data={"metadata": metadata},
            automatic_tax={"enabled": True},
            **customer_kwargs,
        )

        return session

    async def create_portal_session(
        self, db: AsyncSession, user_id: str, return_url: str | None = None
    ) -> str:
        user = await self._user_repo.get_by_id(db, user_id)
        if not user:
            raise BillingServiceError("User not found")

        if not user.stripe_customer_id:
            raise BillingServiceError(
                "Stripe customer not found for this account. Complete a checkout first."
            )

        portal_return_url = return_url or self._stripe_config.config.stripe_portal_return_url
        if not portal_return_url:
            raise BillingConfigurationError(
                "A return URL must be provided for the billing portal session"
            )

        self._stripe_config.ensure_api_key()

        try:
            session = await run_in_threadpool(
                stripe.billing_portal.Session.create,
                customer=user.stripe_customer_id,
                return_url=portal_return_url,
            )
        except stripe.error.StripeError as exc:  # pragma: no cover - network path
            raise BillingServiceError(
                f"Failed to create billing portal session: {exc.user_message or str(exc)}"
            ) from exc

        url = getattr(session, "url", None)
        if not url:
            raise BillingServiceError("Stripe did not return a portal URL")

        return url
