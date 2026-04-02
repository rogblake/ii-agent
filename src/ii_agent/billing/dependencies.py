"""FastAPI dependencies for billing domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.auth.users.dependencies import UserRepositoryDep
from ii_agent.billing.repository import BillingTransactionRepository
from ii_agent.billing.service import BillingService
from ii_agent.billing.stripe_config import StripeConfig
from ii_agent.billing.webhook_handler import StripeWebhookHandler


# ==================== Repository Dependencies ====================


def get_billing_repository() -> BillingTransactionRepository:
    """Provide BillingTransactionRepository instance."""
    return BillingTransactionRepository()


BillingRepositoryDep = Annotated[BillingTransactionRepository, Depends(get_billing_repository)]


# ==================== Config Dependencies ====================


def get_stripe_config() -> StripeConfig:
    """Provide StripeConfig instance."""
    return StripeConfig(config=get_settings())


StripeConfigDep = Annotated[StripeConfig, Depends(get_stripe_config)]


# ==================== Service Dependencies ====================


def get_billing_service(
    stripe_config: StripeConfigDep,
    user_repo: UserRepositoryDep,
) -> BillingService:
    """Provide BillingService instance with explicit repo injection."""
    return BillingService(
        stripe_config=stripe_config,
        user_repo=user_repo,
    )


def get_webhook_handler(
    stripe_config: StripeConfigDep,
    billing_repo: BillingRepositoryDep,
    user_repo: UserRepositoryDep,
) -> StripeWebhookHandler:
    """Provide StripeWebhookHandler instance."""
    return StripeWebhookHandler(
        stripe_config=stripe_config,
        billing_repo=billing_repo,
        user_repo=user_repo,
    )


BillingServiceDep = Annotated[BillingService, Depends(get_billing_service)]
StripeWebhookHandlerDep = Annotated[StripeWebhookHandler, Depends(get_webhook_handler)]
