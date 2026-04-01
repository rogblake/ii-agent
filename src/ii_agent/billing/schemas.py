"""Pydantic schemas for billing domain.

Service-layer DTOs (snake_case) are used as input/output for BillingService.
API-layer schemas (camelCase aliases) are used in router endpoints.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Token Usage (shared billing concept used by chat/llm providers)
# ---------------------------------------------------------------------------


class TokenUsage(BaseModel):
    """Model for token usage tracking."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    model: Optional[str] = None


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PlanId(StrEnum):
    """Subscription plan identifiers."""

    FREE = "free"
    PLUS = "plus"
    PRO = "pro"


class BillingCycle(StrEnum):
    """Billing cycle options."""

    MONTHLY = "monthly"
    ANNUALLY = "annually"


# ---------------------------------------------------------------------------
# Service-layer DTOs (input/output for BillingService)
# ---------------------------------------------------------------------------


class CreateCheckoutParams(BaseModel):
    """Input for ``BillingService.create_checkout_session``."""

    model_config = ConfigDict(frozen=True)

    plan_id: PlanId
    billing_cycle: BillingCycle
    user_id: UUID
    return_url: str | None = None


class CheckoutResult(BaseModel):
    """Output from ``BillingService.create_checkout_session``."""

    session_id: str
    url: str | None = None


class CreatePortalParams(BaseModel):
    """Input for ``BillingService.create_portal_session``."""

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    return_url: str | None = None


class PortalResult(BaseModel):
    """Output from ``BillingService.create_portal_session``."""

    url: str


# ---------------------------------------------------------------------------
# API-layer schemas (camelCase aliases for HTTP endpoints)
# ---------------------------------------------------------------------------


class CheckoutSessionRequest(BaseModel):
    """HTTP request payload for creating a Stripe checkout session."""

    model_config = ConfigDict(populate_by_name=True)

    plan_id: PlanId = Field(alias="planId")
    billing_cycle: BillingCycle = Field(alias="billingCycle")
    return_url: str | None = Field(default=None, alias="returnUrl")


class CheckoutSessionResponse(BaseModel):
    """HTTP response payload after creating a checkout session."""

    model_config = ConfigDict(populate_by_name=True)

    session_id: str | None = Field(default=None, alias="sessionId")
    url: str | None = None


class PortalSessionRequest(BaseModel):
    """HTTP request payload for creating a portal session."""

    model_config = ConfigDict(populate_by_name=True)

    return_url: str | None = Field(default=None, alias="returnUrl")


class PortalSessionResponse(BaseModel):
    """HTTP response payload for Stripe billing portal session."""

    url: str
