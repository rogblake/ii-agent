"""Pydantic schemas for credits API.

Field names match the frontend TypeScript types in ``frontend/src/typings/user.ts``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ii_agent.credits.types import CreditType, TransactionType


# ---------------------------------------------------------------------------
# GET /credits/balance
# ---------------------------------------------------------------------------


class CreditBalanceResponse(BaseModel):
    """Current credit balance for a user."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    credits: float
    bonus_credits: float
    updated_at: datetime


# ---------------------------------------------------------------------------
# GET /credits/usage  (session-level summary)
# ---------------------------------------------------------------------------


class CreditUsageSession(BaseModel):
    """Per-session credit usage summary."""

    session_id: UUID
    session_title: str
    credits: float
    bonus_credits: float
    updated_at: datetime


class CreditUsageResponse(BaseModel):
    """Paginated list of session usage summaries."""

    sessions: list[CreditUsageSession]
    total: int


# ---------------------------------------------------------------------------
# GET /credits/usage/{session_id}  (transaction-level detail)
# ---------------------------------------------------------------------------


class CreditTransactionItem(BaseModel):
    """A single credit transaction record within a session."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_type: TransactionType
    credit_type: CreditType
    amount: float
    balance_after: float
    model_id: Optional[str] = None
    run_id: Optional[UUID] = None
    description: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime


class SessionUsageDetailResponse(BaseModel):
    """Detailed credit transactions for a specific session."""

    session_id: UUID
    session_title: str
    items: list[CreditTransactionItem]
    total_credits: float
    total_items: int


# ---------------------------------------------------------------------------
# GET /credits/history  (paginated full transaction history)
# ---------------------------------------------------------------------------


class CreditHistoryResponse(BaseModel):
    """Paginated credit transaction history."""

    transactions: list[CreditTransactionItem]
    total: int
    page: int
    per_page: int
