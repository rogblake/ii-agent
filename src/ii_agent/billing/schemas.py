"""Pydantic schemas (DTOs) for billing domain."""

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class CheckoutSessionRequest(BaseModel):
    """Request payload for creating a Stripe checkout session."""

    model_config = ConfigDict(populate_by_name=True)

    plan_id: Literal["free", "plus", "pro"] = Field(alias="planId")
    billing_cycle: Literal["monthly", "annually"] = Field(alias="billingCycle")
    return_url: Optional[str] = Field(default=None, alias="returnUrl")


class CheckoutSessionResponse(BaseModel):
    """Response payload returned after creating a checkout session."""

    model_config = ConfigDict(populate_by_name=True)

    session_id: Optional[str] = Field(default=None, alias="sessionId")
    url: Optional[str] = None


class PortalSessionRequest(BaseModel):
    """Request payload for creating a portal session."""

    model_config = ConfigDict(populate_by_name=True)

    return_url: Optional[str] = Field(default=None, alias="returnUrl")


class PortalSessionResponse(BaseModel):
    """Response payload for Stripe billing portal session."""

    url: str
