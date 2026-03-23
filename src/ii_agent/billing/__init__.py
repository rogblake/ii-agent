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

__all__ = [
    # Router
    "router",
    # Exceptions
    "BillingConfigurationError",
    "BillingGatewayError",
    "BillingServiceError",
    "BillingUnsupportedPlanError",
]


def __getattr__(name: str):
    if name == "router":
        from .router import router

        return router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
