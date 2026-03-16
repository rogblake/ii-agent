"""FastAPI dependencies for reservation billing."""

from typing import Annotated

from fastapi import Depends

from ii_agent.billing.credits.dependencies import (
    CreditBalanceRepositoryDep,
    CreditLedgerRepositoryDep,
    CreditServiceDep,
)
from ii_agent.billing.reservations.repository import CreditReservationRepository
from ii_agent.billing.reservations.service import CreditReservationService
from ii_agent.billing.usage.dependencies import UsageServiceDep


def get_credit_reservation_repository() -> CreditReservationRepository:
    """Provide CreditReservationRepository instance."""
    return CreditReservationRepository()


CreditReservationRepositoryDep = Annotated[
    CreditReservationRepository,
    Depends(get_credit_reservation_repository),
]


def get_credit_reservation_service(
    balance_repo: CreditBalanceRepositoryDep,
    ledger_repo: CreditLedgerRepositoryDep,
    reservation_repo: CreditReservationRepositoryDep,
    credit_service: CreditServiceDep,
    usage_service: UsageServiceDep,
) -> CreditReservationService:
    """Provide CreditReservationService instance."""
    return CreditReservationService(
        balance_repo=balance_repo,
        ledger_repo=ledger_repo,
        reservation_repo=reservation_repo,
        credit_service=credit_service,
        usage_service=usage_service,
    )


CreditReservationServiceDep = Annotated[
    CreditReservationService,
    Depends(get_credit_reservation_service),
]
