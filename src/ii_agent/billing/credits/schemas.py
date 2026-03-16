"""Pydantic schemas (DTOs) for credits domain."""

from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class CreditBalance(BaseModel):
    """User's current credit balance."""

    user_id: str
    credits: float = Field(description="Current credit balance")
    bonus_credits: float = Field(
        description="Current bonus credit balance", default=0.0
    )
    updated_at: datetime


class SessionCreditHistory(BaseModel):
    """Credit history for a specific session."""

    session_id: str
    session_title: str = Field(description="Name/title of the session")
    credits: float = Field(description="Total credits used in this session (negative for deductions)")
    updated_at: datetime = Field(description="When the session was last updated")


class CreditHistory(BaseModel):
    """User's credit transaction history with pagination."""

    sessions: List[SessionCreditHistory] = Field(
        description="List of sessions with their credit usage"
    )
    total: int = Field(description="Total number of sessions with credit usage")


class SessionUsageItem(BaseModel):
    """A single usage record within a session."""

    id: int
    billing_kind: str = Field(description="Type of billing event (e.g. llm_usage, tool_usage)")
    source_domain: str
    model_id: Optional[str] = None
    tool_name: Optional[str] = None
    provider: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: Optional[float] = None
    credits_charged: float
    created_at: datetime


class SessionUsageDetail(BaseModel):
    """Detailed usage breakdown for a single session."""

    session_id: str
    session_title: str
    items: List[SessionUsageItem] = Field(description="Individual billing events")
    total_credits: float = Field(description="Total credits charged in this session")
    total_items: int = Field(description="Total number of billing events")


class LedgerEntryResponse(BaseModel):
    """A single credit ledger entry."""

    id: int
    entry_type: str
    source_domain: Optional[str] = None
    source_id: Optional[str] = None
    delta_credits: float
    delta_bonus_credits: float = 0.0
    balance_after_credits: Optional[float] = None
    balance_after_bonus_credits: Optional[float] = None
    idempotency_key: Optional[str] = None
    entry_metadata: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LedgerHistory(BaseModel):
    """Paginated credit ledger history."""

    entries: List[LedgerEntryResponse] = Field(
        description="List of credit ledger entries"
    )
    total: int = Field(description="Total number of ledger entries")


class ReservationResponse(BaseModel):
    """A single credit reservation entry."""

    id: str
    session_id: Optional[str] = None
    source_domain: str
    source_id: str
    billing_kind: str
    quote_strategy: str
    status: str
    model_id: Optional[str] = None
    tool_name: Optional[str] = None
    idempotency_key: Optional[str] = None
    reserved_credits: float
    reserved_bonus_credits: float
    actual_credits: Optional[float] = None
    actual_bonus_credits: Optional[float] = None
    released_credits: Optional[float] = None
    released_bonus_credits: Optional[float] = None
    quoted_usd: float
    max_usd: float
    actual_usd: Optional[float] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReservationHistory(BaseModel):
    """Paginated reservation history."""

    entries: List[ReservationResponse] = Field(
        description="List of credit reservations"
    )
    total: int = Field(description="Total number of reservations")
