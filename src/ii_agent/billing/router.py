"""Billing API endpoints.

This module provides billing-related endpoints for Stripe integration,
including checkout sessions, webhooks, and portal sessions.
"""

from __future__ import annotations

from typing import Optional

import stripe
from fastapi import APIRouter, Request, Response

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.billing.dependencies import BillingServiceDep, StripeWebhookHandlerDep
from ii_agent.billing.exceptions import BillingGatewayError
from ii_agent.billing.schemas import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    PortalSessionRequest,
    PortalSessionResponse,
)
from ii_agent.billing.service import CheckoutSessionParams


router = APIRouter(prefix="/billing", tags=["Billing"])


@router.post("/checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    payload: CheckoutSessionRequest,
    current_user: CurrentUser,
    billing_service: BillingServiceDep,
    db: DBSession,
) -> CheckoutSessionResponse:
    """Create a Stripe checkout session for the selected plan."""

    try:
        session = await billing_service.create_checkout_session(
            db,
            CheckoutSessionParams(
                plan_id=payload.plan_id,
                billing_cycle=payload.billing_cycle,
                user_id=str(current_user.id),
                return_url=payload.return_url,
            )
        )
    except stripe.error.StripeError as error:  # pragma: no cover - network path
        raise BillingGatewayError(
            error.user_message or "Unable to create checkout session"
        ) from error

    return CheckoutSessionResponse(
        session_id=session.id, url=getattr(session, "url", None)
    )


@router.post("/webhook", status_code=200)
async def stripe_webhook(
    request: Request,
    db: DBSession,
    webhook_handler: StripeWebhookHandlerDep,
) -> Response:
    """Receive and process Stripe webhook events.

    No auth required - Stripe authenticates via signature header.
    """
    payload = await request.body()
    signature = request.headers.get("stripe-signature")

    try:
        event = webhook_handler.construct_webhook_event(payload, signature)
        await webhook_handler.handle_webhook_event(db, event)
    except stripe.error.StripeError as error:  # pragma: no cover - network path
        raise BillingGatewayError(
            error.user_message or "Stripe webhook error"
        ) from error

    return Response(status_code=200)


@router.post("/portal-session", response_model=PortalSessionResponse)
async def create_portal_session(
    payload: Optional[PortalSessionRequest],
    current_user: CurrentUser,
    billing_service: BillingServiceDep,
    db: DBSession,
) -> PortalSessionResponse:
    """Create a Stripe billing portal session for the current user."""

    try:
        url = await billing_service.create_portal_session(
            db, str(current_user.id), payload.return_url if payload else None
        )
        return PortalSessionResponse(url=url)
    except stripe.error.StripeError as error:  # pragma: no cover - network path
        raise BillingGatewayError(
            error.user_message or "Unable to create billing portal session"
        ) from error
