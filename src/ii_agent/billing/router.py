"""Billing API endpoints."""

from __future__ import annotations

import stripe
from fastapi import APIRouter, HTTPException, Request, Response, status

from ii_agent.billing.dependencies import BillingServiceDep
from ii_agent.billing.exceptions import (
    BillingConfigurationError,
    BillingServiceError,
    BillingUnsupportedPlanError,
)
from ii_agent.billing.schemas import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    CreateCheckoutParams,
    CreatePortalParams,
    PortalSessionRequest,
    PortalSessionResponse,
)
from ii_agent.auth.dependencies import CurrentUser

router = APIRouter(prefix="/billing", tags=["Billing"])


@router.post("/checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    payload: CheckoutSessionRequest,
    current_user: CurrentUser,
    billing_service: BillingServiceDep,
) -> CheckoutSessionResponse:
    """Create a Stripe checkout session for the selected plan."""
    try:
        result = await billing_service.create_checkout_session(
            CreateCheckoutParams(
                plan_id=payload.plan_id,
                billing_cycle=payload.billing_cycle,
                user_id=current_user.id,
                return_url=payload.return_url,
            )
        )
    except BillingUnsupportedPlanError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except BillingConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error
    except BillingServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error
    except stripe.error.StripeError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=error.user_message or "Unable to create checkout session",
        ) from error

    return CheckoutSessionResponse(
        session_id=result.session_id,
        url=result.url,
    )


@router.post("/webhook", status_code=200)
async def stripe_webhook(
    request: Request,
    billing_service: BillingServiceDep,
) -> Response:
    """Receive and process Stripe webhook events."""
    payload = await request.body()
    signature = request.headers.get("stripe-signature")

    try:
        event = billing_service.construct_webhook_event(payload, signature)
        await billing_service.handle_webhook_event(event)
    except BillingConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error
    except BillingServiceError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except stripe.error.StripeError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=error.user_message or "Stripe webhook error",
        ) from error

    return Response(status_code=status.HTTP_200_OK)


@router.post("/portal-session", response_model=PortalSessionResponse)
async def create_portal_session(
    payload: PortalSessionRequest | None,
    current_user: CurrentUser,
    billing_service: BillingServiceDep,
) -> PortalSessionResponse:
    """Create a Stripe billing portal session for the current user."""
    try:
        result = await billing_service.create_portal_session(
            CreatePortalParams(
                user_id=current_user.id,
                return_url=payload.return_url if payload else None,
            )
        )
        return PortalSessionResponse(url=result.url)
    except BillingConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error
    except BillingServiceError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except stripe.error.StripeError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=error.user_message or "Unable to create billing portal session",
        ) from error
