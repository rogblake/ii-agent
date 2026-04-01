"""Credits domain — balance management and transaction ledger."""

from ii_agent.credits.constants import MINIMUM_REQUIRED_CREDITS
from ii_agent.credits.models import CreditBalance, CreditTransaction
from ii_agent.credits.repository import (
    CreditBalanceRepository,
    CreditTransactionRepository,
)
from ii_agent.credits.router import router
from ii_agent.credits.schemas import (
    CreditBalanceResponse,
    CreditHistoryResponse,
    CreditTransactionItem,
    CreditUsageResponse,
    CreditUsageSession,
    SessionUsageDetailResponse,
)
from ii_agent.credits.service import CreditService
from ii_agent.credits.types import CreditType, TransactionType
from ii_agent.credits.usage import CreditUsageHandler

__all__ = [
    # Constants
    "MINIMUM_REQUIRED_CREDITS",
    # Models
    "CreditBalance",
    "CreditTransaction",
    # Repository
    "CreditBalanceRepository",
    "CreditTransactionRepository",
    # Router
    "router",
    # Schemas
    "CreditBalanceResponse",
    "CreditHistoryResponse",
    "CreditTransactionItem",
    "CreditUsageResponse",
    "CreditUsageSession",
    "SessionUsageDetailResponse",
    # Service
    "CreditService",
    # Types (enums)
    "CreditType",
    "TransactionType",
    # Usage (event-driven credit deduction)
    "CreditUsageHandler",
]
