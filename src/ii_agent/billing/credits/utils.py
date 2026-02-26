"""Utility functions for credits domain."""

from ii_agent.billing.credits.constants import (
    CREDITS_TO_USD_MULTIPLIER,
    USD_TO_CREDITS_MULTIPLIER,
)


def usd_to_credits(usd_amount: float) -> float:
    """Convert USD amount to II-Agent credits."""
    return float(usd_amount) * USD_TO_CREDITS_MULTIPLIER


def credits_to_usd(credits_amount: float) -> float:
    """Convert II-Agent credits to USD amount."""
    return float(credits_amount) * CREDITS_TO_USD_MULTIPLIER
