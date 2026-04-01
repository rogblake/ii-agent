"""Billing domain module.

Provides Stripe checkout/portal/webhook integration, billing transaction
audit logging, pricing constants, and currency conversion utilities.
"""

from ii_agent.billing.exceptions import (
    BillingConfigurationError,
    BillingDuplicateOperationError,
    BillingException,
    BillingGatewayError,
    BillingReconciliationRequiredError,
    BillingServiceError,
    BillingSettlementFinalError,
    BillingSettlementRetryableError,
    BillingTemporarilyUnavailableError,
    BillingUnsupportedPlanError,
    InsufficientCreditsError,
    StripeConfigError,
)
from ii_agent.billing.models import BillingTransaction
from ii_agent.billing.router import router
from ii_agent.billing.schemas import (
    BillingCycle,
    CheckoutResult,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    CreateCheckoutParams,
    CreatePortalParams,
    PlanId,
    PortalResult,
    PortalSessionRequest,
    PortalSessionResponse,
)
from ii_agent.billing.service import BillingService
from ii_agent.billing.utils import (
    CREDITS_PER_100_USD,
    CREDITS_TO_USD_MULTIPLIER,
    DEFAULT_SIGNUP_BONUS_CREDITS,
    DEFAULT_SIGNUP_CREDITS,
    USD_PER_100_CREDITS,
    USD_TO_CREDITS_MULTIPLIER,
    credits_to_usd,
    usd_to_credits,
)

__all__ = [
    # Service
    "BillingService",
    # Model
    "BillingTransaction",
    # Router
    "router",
    # Enums
    "PlanId",
    "BillingCycle",
    # Service DTOs
    "CreateCheckoutParams",
    "CheckoutResult",
    "CreatePortalParams",
    "PortalResult",
    # API schemas
    "CheckoutSessionRequest",
    "CheckoutSessionResponse",
    "PortalSessionRequest",
    "PortalSessionResponse",
    # Utils (pricing constants + conversion)
    "USD_PER_100_CREDITS",
    "CREDITS_PER_100_USD",
    "USD_TO_CREDITS_MULTIPLIER",
    "CREDITS_TO_USD_MULTIPLIER",
    "DEFAULT_SIGNUP_CREDITS",
    "DEFAULT_SIGNUP_BONUS_CREDITS",
    "usd_to_credits",
    "credits_to_usd",
    # Exceptions
    "BillingException",
    "BillingServiceError",
    "BillingConfigurationError",
    "BillingUnsupportedPlanError",
    "BillingGatewayError",
    "StripeConfigError",
    "InsufficientCreditsError",
    "BillingReconciliationRequiredError",
    "BillingTemporarilyUnavailableError",
    "BillingDuplicateOperationError",
    "BillingSettlementRetryableError",
    "BillingSettlementFinalError",
]
