"""Utility functions and constants for billing domain."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ii_agent.core.logger import logger

# ---------------------------------------------------------------------------
# Pricing constants
# ---------------------------------------------------------------------------

# Pricing contract: 100 II-Agent credits == $1.5 USD
USD_PER_100_CREDITS = Decimal("1.5")
CREDITS_PER_100_USD = Decimal("100")

# Derived multipliers (conversion functions below compute via
# numerator/denominator to avoid repeating-decimal loss).
USD_TO_CREDITS_MULTIPLIER = CREDITS_PER_100_USD / USD_PER_100_CREDITS  # ~66.666...
CREDITS_TO_USD_MULTIPLIER = USD_PER_100_CREDITS / CREDITS_PER_100_USD  # 0.015

# Default signup credits
DEFAULT_SIGNUP_CREDITS = 300.0
DEFAULT_SIGNUP_BONUS_CREDITS = 0.0


# ---------------------------------------------------------------------------
# Conversion functions
# ---------------------------------------------------------------------------


def usd_to_credits(usd_amount: float | Decimal) -> Decimal:
    """Convert USD amount to II-Agent credits.

    Computes ``amount * 100 / 1.5`` left-to-right in Decimal arithmetic
    so the intermediate product has a finite representation -- avoiding the
    repeating-decimal precision loss from a pre-computed 66.666... multiplier.
    """
    return Decimal(str(usd_amount)) * CREDITS_PER_100_USD / USD_PER_100_CREDITS


def credits_to_usd(credits_amount: float | Decimal) -> Decimal:
    """Convert II-Agent credits to USD amount.

    Same left-to-right Decimal strategy as :func:`usd_to_credits`.
    """
    return Decimal(str(credits_amount)) * USD_PER_100_CREDITS / CREDITS_PER_100_USD


# ---------------------------------------------------------------------------
# Storybook billing finalization (stub)
# ---------------------------------------------------------------------------


async def finalize_storybook_async_operation(
    *,
    reservation_service: Any,
    scope: Any,
    reservation_id: str,
    result: Any | None = None,
    release_reason: str = "unused",
    settlement_error: str | None = None,
) -> None:
    """Settle or release a credit reservation for a storybook async operation.

    This is a placeholder stub. The credit reservation system was removed
    during the DDD refactoring. Once the reservation infrastructure is
    re-introduced, this function should delegate to the reservation service
    to either settle (when ``result`` is provided) or release the hold.
    """
    logger.warning(
        "finalize_storybook_async_operation called but reservation system is not yet migrated "
        "(reservation_id={}, release_reason={})",
        reservation_id,
        release_reason,
    )
