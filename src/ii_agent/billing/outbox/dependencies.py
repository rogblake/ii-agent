"""Dependencies for durable billing usage facts."""

from typing import Annotated

from fastapi import Depends

from ii_agent.billing.outbox.repository import BillingUsageFactRepository
from ii_agent.billing.outbox.service import BillingUsageFactService
from ii_agent.billing.reservations.dependencies import (
    CreditReservationRepositoryDep,
    CreditReservationServiceDep,
)


def get_billing_usage_fact_repository() -> BillingUsageFactRepository:
    """Provide BillingUsageFactRepository instance."""
    return BillingUsageFactRepository()


BillingUsageFactRepositoryDep = Annotated[
    BillingUsageFactRepository,
    Depends(get_billing_usage_fact_repository),
]


def get_billing_usage_fact_service(
    repository: BillingUsageFactRepositoryDep,
    reservation_repository: CreditReservationRepositoryDep,
    reservation_service: CreditReservationServiceDep,
) -> BillingUsageFactService:
    """Provide BillingUsageFactService instance."""
    return BillingUsageFactService(
        repository=repository,
        reservation_repository=reservation_repository,
        reservation_service=reservation_service,
    )


BillingUsageFactServiceDep = Annotated[
    BillingUsageFactService,
    Depends(get_billing_usage_fact_service),
]
