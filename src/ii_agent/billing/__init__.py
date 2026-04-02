"""Stripe billing and subscriptions domain module.

Import pattern (use full paths to avoid circular imports):
    from ii_agent.billing.models import BillingTransaction
    from ii_agent.billing.repository import BillingTransactionRepository
    from ii_agent.billing.service import BillingService, CheckoutSessionParams
    from ii_agent.billing.dependencies import BillingServiceDep
    from ii_agent.billing.router import router
"""

from .exceptions import (
    BillingConfigurationError,
    BillingGatewayError,
    BillingServiceError,
    BillingUnsupportedPlanError,
)
from .router import router

__all__ = [
    # Router
    "router",
    # Exceptions
    "BillingConfigurationError",
    "BillingGatewayError",
    "BillingServiceError",
    "BillingUnsupportedPlanError",
]
