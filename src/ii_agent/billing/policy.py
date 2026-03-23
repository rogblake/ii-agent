"""Shared billing policy helpers."""

from __future__ import annotations

from decimal import Decimal

CONTROLLED_SHORTFALL_MAX_CREDITS = Decimal("50")
_MIN_POSITIVE_BALANCE_CREDITS = Decimal("1")


def normalized_credit_amount(value: Decimal | float | int) -> Decimal:
    """Normalize a credit amount to Decimal once at the boundary."""
    return Decimal(str(value))


def controlled_shortfall_budget_credits(available_credits: Decimal | float | int) -> Decimal:
    """Return the effective reserve-time budget after applying the shortfall window."""
    available = normalized_credit_amount(available_credits)
    if available > 0:
        return available + CONTROLLED_SHORTFALL_MAX_CREDITS
    return available


def controlled_shortfall_admission_allowed(
    *,
    available_credits: Decimal | float | int,
    required_credits: Decimal | float | int,
) -> bool:
    """Return whether reserve-time admission is allowed under the shortfall policy."""
    available = normalized_credit_amount(available_credits)
    required = normalized_credit_amount(required_credits)
    return available > 0 and controlled_shortfall_budget_credits(available) >= required


def controlled_shortfall_required_credits(
    required_credits: Decimal | float | int,
) -> Decimal:
    """Return the user-visible minimum needed when admission exceeds the shortfall window."""
    required = normalized_credit_amount(required_credits)
    return max(_MIN_POSITIVE_BALANCE_CREDITS, required - CONTROLLED_SHORTFALL_MAX_CREDITS)
