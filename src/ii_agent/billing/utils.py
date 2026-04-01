"""Utility functions and constants for billing domain."""

from __future__ import annotations

from decimal import Decimal

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
