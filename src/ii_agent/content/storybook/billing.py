"""Reusable billing helpers for storybook-originated operations."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.exceptions import InsufficientCreditsError
from ii_agent.billing.types import BillingContextValue, BillingScope
from ii_agent.credits.service import CreditService
from ii_agent.credits.types import TransactionType

DEFAULT_STORYBOOK_IMAGE_RESERVE_USD = Decimal("0.02")
DEFAULT_STORYBOOK_VOICE_PAGE_RESERVE_USD = Decimal("0.02")


def build_storybook_scope(
    *,
    user_id: str,
    session_id: str,
    run_id: str | None = None,
) -> BillingScope:
    """Build the canonical billing scope for storybook flows."""
    return BillingScope.for_session(
        user_id=user_id,
        app_kind="chat",
        session_id=session_id,
        billing_context=BillingContextValue.STORYBOOK,
        run_id=run_id,
    )


async def check_and_deduct_storybook_credits(
    db: AsyncSession,
    *,
    credit_service: CreditService,
    scope: BillingScope,
    amount_usd: float | Decimal,
    tool_name: str,
    metadata: dict | None = None,
) -> None:
    """Check credits and deduct for a storybook operation.

    Raises InsufficientCreditsError when the user cannot afford the charge.
    """
    amount = float(amount_usd)
    if amount <= 0:
        return

    has_credits = await credit_service.has_sufficient_credits(
        db, scope.user_id, amount
    )
    if not has_credits:
        raise InsufficientCreditsError(
            available_credits=0.0,
            required_credits=amount,
        )

    tx_metadata = scope.billing_metadata()
    if metadata:
        tx_metadata.update(metadata)
    tx_metadata["tool_name"] = tool_name

    await credit_service.deduct(
        db,
        user_id=scope.user_id,
        amount=amount,
        transaction_type=TransactionType.TOOL_USAGE,
        session_id=scope.session_id,
        run_id=scope.run_id,
        description=f"storybook:{tool_name}",
        metadata=tx_metadata,
    )
