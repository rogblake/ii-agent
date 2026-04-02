"""Stripe webhook event handling."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import stripe
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.repository import BillingTransactionRepository
from ii_agent.billing.exceptions import BillingConfigurationError, BillingServiceError
from ii_agent.billing.stripe_config import StripeConfig
from ii_agent.auth.users.repository import UserRepository


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SubscriptionContext:
    """Resolved subscription metadata shared across webhook handlers."""

    subscription: dict[str, Any] | None
    user_id: str | None
    plan_id: str | None
    billing_cycle: str | None
    customer_id: str | None
    period_end: int | None
    credits: float | None


class StripeWebhookHandler:
    """Handles Stripe webhook events: checkout, invoice, subscription updates."""

    _EVENT_HANDLERS: dict[str, str] = {
        "checkout.session.completed": "_handle_checkout_session_completed",
        "invoice.payment_succeeded": "_handle_invoice_payment_succeeded",
        "customer.subscription.deleted": "_handle_subscription_deleted",
        "customer.subscription.updated": "_handle_subscription_updated",
    }

    def __init__(
        self,
        *,
        stripe_config: StripeConfig,
        billing_repo: BillingTransactionRepository,
        user_repo: UserRepository,
    ) -> None:
        self._stripe_config = stripe_config
        self._billing_repo = billing_repo
        self._user_repo = user_repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def construct_webhook_event(
        self, payload: bytes, signature: str | None
    ) -> stripe.Event:
        if not self._stripe_config.config.stripe.webhook_secret:
            raise BillingConfigurationError("Stripe webhook secret is not configured")
        if not signature:
            raise BillingServiceError("Missing Stripe signature header")

        self._stripe_config.ensure_api_key()

        try:
            return stripe.Webhook.construct_event(
                payload, signature, self._stripe_config.config.stripe.webhook_secret
            )
        except ValueError as exc:
            raise BillingServiceError("Invalid Stripe webhook payload") from exc
        except stripe.error.SignatureVerificationError as exc:
            raise BillingServiceError("Invalid Stripe signature") from exc

    async def handle_webhook_event(self, db: AsyncSession, event: stripe.Event) -> None:
        event_type = event.get("type")
        event_id = event.get("id")
        data_object = event.get("data", {}).get("object")

        logger.info("Processing Stripe event %s (%s)", event_id, event_type)

        handler_name = self._EVENT_HANDLERS.get(event_type)
        if handler_name:
            await getattr(self, handler_name)(db, event_id, data_object)
        else:
            logger.debug("Unhandled Stripe event type: %s", event_type)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _record_transaction(
        self,
        db: AsyncSession,
        *,
        event_id: str | None,
        user_id: str,
        values: dict[str, Any],
    ) -> None:
        if not event_id:
            logger.warning(
                "Skipping billing transaction for user %s due to missing event id",
                user_id,
            )
            return

        existing = await self._billing_repo.get_by_event_id(db, event_id)
        if existing:
            logger.debug(
                "Billing transaction already exists for event %s", event_id
            )
            return

        await self._billing_repo.create(
            db,
            user_id=user_id,
            stripe_event_id=event_id,
            **values,
        )
        logger.info(
            "Stored billing transaction for user %s (event %s)",
            user_id,
            event_id,
        )

    async def _retrieve_subscription(
        self, subscription_id: str | None
    ) -> dict[str, Any] | None:
        if not subscription_id:
            return None

        self._stripe_config.ensure_api_key()

        try:
            subscription = await run_in_threadpool(
                stripe.Subscription.retrieve, subscription_id
            )
            return self._stripe_config.as_dict(subscription)
        except stripe.error.StripeError as exc:  # pragma: no cover - network path
            logger.error("Failed to retrieve subscription %s: %s", subscription_id, exc)
            return None

    async def _resolve_subscription_context(
        self,
        *,
        subscription_id: str | None,
        user_id: str | None = None,
        plan_id: str | None = None,
        billing_cycle: str | None = None,
        customer_id: str | None = None,
    ) -> SubscriptionContext:
        subscription = await self._retrieve_subscription(subscription_id)

        if subscription:
            sub_meta = subscription.get("metadata", {}) or {}
            user_id = user_id or sub_meta.get("user_id")
            plan_id = plan_id or sub_meta.get("plan_id")
            billing_cycle = billing_cycle or sub_meta.get("billing_cycle")
            customer_id = customer_id or subscription.get("customer")

            items = subscription.get("items", {}).get("data", []) or []
            first_item = items[0] if items else {}
            price_id = (first_item.get("price") or {}).get("id")

            if price_id and (not plan_id or not billing_cycle):
                mapped = self._stripe_config.plan_cycle_from_price(price_id)
                if mapped:
                    plan_id = plan_id or mapped[0]
                    billing_cycle = billing_cycle or mapped[1]

            period_end = (
                first_item.get("current_period_end")
                or subscription.get("current_period_end")
            )
        else:
            period_end = None

        return SubscriptionContext(
            subscription=subscription,
            user_id=user_id,
            plan_id=plan_id,
            billing_cycle=billing_cycle,
            customer_id=customer_id,
            period_end=period_end,
            credits=self._stripe_config.plan_credits(plan_id),
        )

    # ------------------------------------------------------------------
    # Webhook event handlers
    # ------------------------------------------------------------------
    async def _handle_checkout_session_completed(
        self, db: AsyncSession, event_id: str | None, session_object: Any
    ) -> None:
        session_data = self._stripe_config.as_dict(session_object)
        metadata = session_data.get("metadata", {}) or {}

        user_id = metadata.get("user_id")
        if not user_id:
            logger.warning(
                "Checkout session %s missing user or plan metadata", event_id
            )
            return

        ctx = await self._resolve_subscription_context(
            subscription_id=session_data.get("subscription"),
            user_id=user_id,
            plan_id=metadata.get("plan_id"),
            billing_cycle=metadata.get("billing_cycle"),
            customer_id=session_data.get("customer"),
        )

        status = (
            ctx.subscription.get("status")
            if ctx.subscription
            else session_data.get("status")
        )

        user = await self._user_repo.get_by_id(db, user_id)
        if not user:
            logger.warning(
                "User %s not found for checkout session completion", user_id,
            )
            return

        await self._user_repo.update_subscription(
            db,
            user,
            subscription_plan=metadata.get("plan_id"),
            subscription_status=status,
            subscription_billing_cycle=ctx.billing_cycle if ctx.billing_cycle else ...,
            stripe_customer_id=ctx.customer_id,
            subscription_current_period_end=self._stripe_config.to_datetime(ctx.period_end) if ctx.period_end else None,
            credits=ctx.credits,
        )

        logger.info(
            "Updated subscription for user %s via checkout completion: plan=%s, status=%s",
            user_id,
            ctx.plan_id,
            status,
        )

        await self._record_transaction(
            db,
            event_id=event_id or session_data.get("id"),
            user_id=user_id,
            values={
                "stripe_object_id": session_data.get("id"),
                "stripe_customer_id": ctx.customer_id,
                "stripe_subscription_id": session_data.get("subscription"),
                "plan_id": ctx.plan_id,
                "billing_cycle": ctx.billing_cycle,
                "status": status,
                "raw_payload": session_data,
            },
        )

    async def _handle_invoice_payment_succeeded(
        self, db: AsyncSession, event_id: str | None, invoice_object: Any
    ) -> None:
        invoice_data = self._stripe_config.as_dict(invoice_object)
        invoice_id = invoice_data.get("id")
        metadata = invoice_data.get("metadata", {}) or {}

        ctx = await self._resolve_subscription_context(
            subscription_id=invoice_data.get("subscription"),
            user_id=metadata.get("user_id"),
            plan_id=metadata.get("plan_id"),
            billing_cycle=metadata.get("billing_cycle"),
            customer_id=invoice_data.get("customer"),
        )

        user_id = ctx.user_id
        if not user_id and ctx.customer_id:
            user_id = await self._user_repo.lookup_by_customer_id(db, ctx.customer_id)

        if not user_id:
            logger.warning(
                "Invoice payment event %s missing user identification", event_id
            )
            return

        # Fall back to invoice line items for plan resolution
        plan_id = ctx.plan_id
        billing_cycle = ctx.billing_cycle
        if not plan_id:
            line_items = invoice_data.get("lines", {}).get("data", [])
            if line_items:
                price = (line_items[0] or {}).get("price") or {}
                price_id = price.get("id")
                mapped = self._stripe_config.plan_cycle_from_price(price_id)
                if mapped:
                    plan_id, inferred_cycle = mapped
                    billing_cycle = billing_cycle or inferred_cycle

        credits = self._stripe_config.plan_credits(plan_id) if plan_id != ctx.plan_id else ctx.credits
        amount_paid = invoice_data.get("amount_paid")
        currency = invoice_data.get("currency")
        status = invoice_data.get("status")

        user = await self._user_repo.get_by_id(db, user_id)
        if not user:
            logger.warning("User %s not found for invoice event", user_id)
            return

        resolved_status = (
            ctx.subscription.get("status", status) if ctx.subscription else status
        )
        await self._user_repo.update_subscription(
            db,
            user,
            subscription_plan=plan_id,
            subscription_status=resolved_status,
            subscription_billing_cycle=billing_cycle if billing_cycle else ...,
            stripe_customer_id=ctx.customer_id,
            subscription_current_period_end=self._stripe_config.to_datetime(ctx.period_end) if ctx.period_end else None,
            credits=credits,
        )

        await self._record_transaction(
            db,
            event_id=event_id or invoice_id,
            user_id=user_id,
            values={
                "stripe_object_id": invoice_id,
                "stripe_customer_id": ctx.customer_id,
                "stripe_subscription_id": invoice_data.get("subscription"),
                "stripe_invoice_id": invoice_id,
                "stripe_payment_intent_id": invoice_data.get("payment_intent"),
                "amount": (amount_paid or 0) / 100 if amount_paid is not None else None,
                "currency": currency,
                "plan_id": plan_id,
                "billing_cycle": billing_cycle,
                "credits": credits,
                "status": status,
                "raw_payload": self._stripe_config.as_dict(invoice_data),
            },
        )

        logger.info(
            "Recorded billing transaction for user %s: invoice=%s, plan=%s, amount=%s",
            user_id,
            invoice_id,
            plan_id,
            (amount_paid or 0) / 100 if amount_paid is not None else None,
        )

    async def _handle_subscription_deleted(
        self, db: AsyncSession, event_id: str | None, subscription_object: Any
    ) -> None:
        subscription_data = self._stripe_config.as_dict(subscription_object)
        metadata = subscription_data.get("metadata", {}) or {}
        user_id = metadata.get("user_id")
        customer_id = subscription_data.get("customer")

        if not user_id and customer_id:
            user_id = await self._user_repo.lookup_by_customer_id(db, customer_id)

        if not user_id:
            logger.warning(
                "Subscription cancel event %s missing user identification", event_id
            )
            return

        status = subscription_data.get("status") or "canceled"
        period_end = subscription_data.get(
            "current_period_end"
        ) or subscription_data.get("canceled_at")

        user = await self._user_repo.get_by_id(db, user_id)
        if not user:
            logger.warning(
                "Could not update canceled subscription for missing user %s",
                user_id,
            )
            return

        await self._user_repo.update_subscription(
            db,
            user,
            subscription_status=status,
            subscription_plan="free",
            subscription_billing_cycle=None,
            credits=self._stripe_config.config.credits.default_user_credits,
            subscription_current_period_end=self._stripe_config.to_datetime(period_end) if period_end else None,
        )

        logger.info(
            "Marked subscription canceled for user %s via event %s",
            user_id,
            event_id,
        )

        items = subscription_data.get("items", {}).get("data", []) or []
        first_plan = items[0].get("plan", {}) if items else {}
        billing_cycle = first_plan.get("interval")

        await self._record_transaction(
            db,
            event_id=event_id or subscription_data.get("id"),
            user_id=user_id,
            values={
                "stripe_object_id": subscription_data.get("id"),
                "stripe_customer_id": customer_id,
                "stripe_subscription_id": subscription_data.get("id"),
                "status": status,
                "plan_id": "free",
                "billing_cycle": billing_cycle,
                "raw_payload": subscription_data,
            },
        )

    async def _handle_subscription_updated(
        self, db: AsyncSession, event_id: str | None, subscription_object: Any
    ) -> None:
        subscription_data = self._stripe_config.as_dict(subscription_object)
        metadata = subscription_data.get("metadata", {}) or {}
        user_id = metadata.get("user_id")
        plan_id = metadata.get("plan_id")
        billing_cycle = metadata.get("billing_cycle")
        customer_id = subscription_data.get("customer")

        items = subscription_data.get("items", {}).get("data", []) or []
        first_item = items[0] if items else {}
        price = first_item.get("price") or {}
        price_id = price.get("id")

        if price_id:
            mapped = self._stripe_config.plan_cycle_from_price(price_id)
            if mapped:
                mapped_plan_id, mapped_cycle = mapped
                plan_id = mapped_plan_id
                billing_cycle = billing_cycle or mapped_cycle

        if not billing_cycle:
            recurring = price.get("recurring") or {}
            interval = recurring.get("interval")
            if interval:
                billing_cycle = billing_cycle or interval
            elif first_item:
                plan_interval = (first_item.get("plan") or {}).get("interval")
                if plan_interval:
                    billing_cycle = plan_interval

        if not user_id and customer_id:
            user_id = await self._user_repo.lookup_by_customer_id(db, customer_id)

        if not user_id:
            logger.warning(
                "Subscription update event %s missing user identification", event_id
            )
            return

        status = subscription_data.get("status")
        period_end = subscription_data.get("current_period_end")
        credits = self._stripe_config.plan_credits(plan_id)

        user = await self._user_repo.get_by_id(db, user_id)
        if not user:
            logger.warning(
                "Could not update subscription for missing user %s", user_id
            )
            return

        await self._user_repo.update_subscription(
            db,
            user,
            subscription_plan=plan_id,
            subscription_status=status,
            subscription_billing_cycle=billing_cycle if billing_cycle else ...,
            stripe_customer_id=customer_id,
            subscription_current_period_end=self._stripe_config.to_datetime(period_end) if period_end else None,
            credits=credits,
        )

        logger.info(
            "Updated subscription for user %s via subscription updated event: plan=%s, status=%s",
            user_id,
            plan_id,
            status,
        )

        await self._record_transaction(
            db,
            event_id=event_id or subscription_data.get("id"),
            user_id=user_id,
            values={
                "stripe_object_id": subscription_data.get("id"),
                "stripe_customer_id": customer_id,
                "stripe_subscription_id": subscription_data.get("id"),
                "plan_id": plan_id,
                "billing_cycle": billing_cycle,
                "credits": credits,
                "status": status,
                "raw_payload": subscription_data,
            },
        )
