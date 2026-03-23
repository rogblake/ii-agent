"""Credits and subscription management domain module."""

from __future__ import annotations

from ii_agent.billing.credits.balance_models import CreditBalanceRecord
from ii_agent.billing.credits.balance_repository import CreditBalanceRepository
from ii_agent.billing.credits.dependencies import CreditServiceDep
from ii_agent.billing.credits.exceptions import CreditBalanceNotFoundError
from ii_agent.billing.credits.ledger_models import CreditLedgerEntry
from ii_agent.billing.credits.ledger_repository import CreditLedgerRepository
from ii_agent.billing.credits.schemas import (
    CreditBalance,
    CreditHistory,
    LedgerEntryResponse,
    LedgerHistory,
    SessionCreditHistory,
)
from ii_agent.billing.credits.service import CreditService

__all__ = [
    "CreditBalanceRecord",
    "CreditBalanceRepository",
    "CreditBalanceNotFoundError",
    "CreditLedgerEntry",
    "CreditLedgerRepository",
    "CreditService",
    "CreditServiceDep",
    "router",
    "CreditBalance",
    "CreditHistory",
    "LedgerEntryResponse",
    "LedgerHistory",
    "SessionCreditHistory",
]


def __getattr__(name: str):
    if name == "router":
        from ii_agent.billing.credits.router import router

        return router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
