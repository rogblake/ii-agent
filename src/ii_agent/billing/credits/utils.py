"""Utility functions for credits domain."""

from decimal import Decimal

from ii_agent.billing.credits.constants import (
    CREDITS_PER_100_USD,
    USD_PER_100_CREDITS,
)


def usd_to_credits(usd_amount: float | Decimal) -> Decimal:
    """Convert USD amount to II-Agent credits.

    Computes ``amount * 100 / 1.5`` left-to-right in Decimal arithmetic
    so the intermediate product has a finite representation — avoiding the
    repeating-decimal precision loss from a pre-computed 66.666… multiplier.
    """
    return Decimal(str(usd_amount)) * CREDITS_PER_100_USD / USD_PER_100_CREDITS


def credits_to_usd(credits_amount: float | Decimal) -> Decimal:
    """Convert II-Agent credits to USD amount.

    Same left-to-right Decimal strategy as :func:`usd_to_credits`.
    """
    return Decimal(str(credits_amount)) * USD_PER_100_CREDITS / CREDITS_PER_100_USD
