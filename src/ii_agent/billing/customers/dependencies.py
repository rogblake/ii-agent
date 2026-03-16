"""FastAPI dependencies for billing customers domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.billing.customers.repository import BillingCustomerRepository
from ii_agent.billing.customers.service import BillingCustomerService


def get_billing_customer_repository() -> BillingCustomerRepository:
    """Provide BillingCustomerRepository instance."""
    return BillingCustomerRepository()


BillingCustomerRepositoryDep = Annotated[
    BillingCustomerRepository, Depends(get_billing_customer_repository)
]


def get_billing_customer_service(
    customer_repo: BillingCustomerRepositoryDep,
) -> BillingCustomerService:
    """Provide BillingCustomerService instance."""
    return BillingCustomerService(customer_repo=customer_repo)


BillingCustomerServiceDep = Annotated[
    BillingCustomerService, Depends(get_billing_customer_service)
]
