"""FastAPI dependencies for credits domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.billing.credits.balance_repository import CreditBalanceRepository
from ii_agent.billing.credits.ledger_repository import CreditLedgerRepository
from ii_agent.billing.credits.service import CreditService


def get_credit_ledger_repository() -> CreditLedgerRepository:
    """Provide CreditLedgerRepository instance."""
    return CreditLedgerRepository()


CreditLedgerRepositoryDep = Annotated[
    CreditLedgerRepository, Depends(get_credit_ledger_repository)
]


def get_credit_balance_repository() -> CreditBalanceRepository:
    """Provide CreditBalanceRepository instance."""
    return CreditBalanceRepository()


CreditBalanceRepositoryDep = Annotated[
    CreditBalanceRepository, Depends(get_credit_balance_repository)
]


def get_credit_service(
    balance_repo: CreditBalanceRepositoryDep,
    ledger_repo: CreditLedgerRepositoryDep,
) -> CreditService:
    """Provide CreditService instance with explicit repo injection."""
    return CreditService(
        balance_repo=balance_repo, ledger_repo=ledger_repo
    )


CreditServiceDep = Annotated[CreditService, Depends(get_credit_service)]
