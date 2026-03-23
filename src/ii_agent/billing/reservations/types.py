"""Typed billing quote and settlement values."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ii_agent.billing.exceptions import BillingDuplicateOperationError


class ReservationStatus(str, enum.Enum):
    """Lifecycle states for a credit reservation."""

    RESERVED = "reserved"
    SETTLED = "settled"
    RELEASED = "released"
    EXPIRED = "expired"
    SETTLEMENT_FAILED = "settlement_failed"


class BillingKind(str, enum.Enum):
    """What kind of billable work a reservation covers."""

    LLM_USAGE = "llm_usage"
    TOOL_USAGE = "tool_usage"


class SourceDomain(str, enum.Enum):
    """Origin of a billing event (ledger or reservation)."""

    CHAT_LLM = "chat_llm"
    AGENT_LLM = "agent_llm"
    CHAT_TOOL = "chat_tool"
    AGENT_TOOL = "agent_tool"
    VOICE_GENERATION = "voice_generation"
    IMAGE_GENERATION = "image_generation"
    WEBHOOK = "webhook"
    CRON = "cron"


class QuoteStrategy(str, enum.Enum):
    """How the upfront cost was estimated."""

    EXACT = "exact"
    BOUNDED = "bounded"
    POST_FACTO = "post_facto"


SETTLEMENT_ERROR_SHORTFALL_UNRECONCILED = "settlement_shortfall_unreconciled"


class BillingQuote(BaseModel):
    """Upfront cost quote for a prepaid billable operation."""

    strategy: Literal["exact", "bounded", "post_facto"] = "bounded"
    reserve_usd: Decimal = Field(default=Decimal("0"))
    max_usd: Decimal = Field(default=Decimal("0"))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_amounts(self) -> "BillingQuote":
        self.reserve_usd = Decimal(str(self.reserve_usd))
        self.max_usd = Decimal(str(self.max_usd))
        if self.reserve_usd < 0 or self.max_usd < 0:
            raise ValueError("BillingQuote amounts must be non-negative")
        if self.max_usd < self.reserve_usd:
            raise ValueError("BillingQuote.max_usd must be >= reserve_usd")
        return self


@dataclass(frozen=True)
class ReservationHold:
    """Persisted credit hold returned after a successful reserve call."""

    reservation_id: str
    idempotency_key: str
    reserved_credits: Decimal
    reserved_bonus_credits: Decimal
    quoted_usd: Decimal
    max_usd: Decimal
    output_token_cap: int | None = None
    status: ReservationStatus = ReservationStatus.RESERVED
    was_created: bool = True

    @property
    def total_reserved(self) -> Decimal:
        return self.reserved_credits + self.reserved_bonus_credits


def raise_if_duplicate_operation(hold: ReservationHold | None) -> None:
    """Raise when an idempotent reservation lookup returns prior work."""
    if hold is None or hold.was_created:
        return

    status = hold.status.value if isinstance(hold.status, ReservationStatus) else str(hold.status)
    if hold.status == ReservationStatus.RESERVED:
        message = "Billing operation key is already in progress"
    else:
        message = "Billing operation key has already been finalized"

    raise BillingDuplicateOperationError(
        message,
        reservation_id=hold.reservation_id,
        reservation_status=status,
    )


@dataclass(frozen=True)
class BillingSettlementResult:
    """Final settlement outcome for a reservation."""

    reservation_id: str
    status: ReservationStatus
    charged_credits: Decimal = Decimal("0")
    charged_bonus_credits: Decimal = Decimal("0")
    released_credits: Decimal = Decimal("0")
    released_bonus_credits: Decimal = Decimal("0")
    usage_record_id: int | None = None
    shortfall_detected: bool = False

    @property
    def total_charged(self) -> Decimal:
        return self.charged_credits + self.charged_bonus_credits
