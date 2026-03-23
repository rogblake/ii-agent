"""Reusable billing helpers for storybook-originated operations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from decimal import Decimal
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.operations import (
    build_billing_settlement_inputs,
    finalize_billing_operation,
    reserve_billing_operation,
    run_billed_operation,
)
from ii_agent.billing.types import (
    BillingContextValue,
    BillingReservationRequest,
    BillingResult,
    BillingScope,
)
from ii_agent.billing.reservations.service import CreditReservationService
from ii_agent.billing.reservations.types import BillingKind, BillingQuote, QuoteStrategy
from ii_agent.core.db.manager import get_db_session_local

DEFAULT_STORYBOOK_IMAGE_RESERVE_USD = Decimal("0.02")
DEFAULT_STORYBOOK_VOICE_PAGE_RESERVE_USD = Decimal("0.02")

_T = TypeVar("_T")


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


def build_storybook_request(
    *,
    scope: BillingScope,
    namespace: str,
    operation_id: str,
    source_domain: str,
    tool_name: str,
    reserve_usd: Decimal | float | int,
    max_usd: Decimal | float | int | None = None,
    metadata: dict | None = None,
    explicit_idempotency_key: str | None = None,
) -> BillingReservationRequest:
    """Construct a bounded reservation request for one storybook operation."""
    reserve_amount = Decimal(str(reserve_usd))
    max_amount = Decimal(str(max_usd if max_usd is not None else reserve_amount))
    return BillingReservationRequest(
        source_domain=source_domain,
        source_id=operation_id,
        billing_kind=BillingKind.TOOL_USAGE,
        quote=BillingQuote(
            strategy=QuoteStrategy.BOUNDED.value,
            reserve_usd=reserve_amount,
            max_usd=max_amount,
            metadata=metadata or {},
        ),
        tool_name=tool_name,
        idempotency_key=explicit_idempotency_key
        or scope.build_operation_key(namespace, operation_id),
        metadata=metadata or {},
    )


async def reserve_storybook_operation(
    db: AsyncSession,
    *,
    reservation_service: CreditReservationService,
    scope: BillingScope,
    request: BillingReservationRequest,
):
    """Create one storybook reservation using the canonical scope metadata."""
    return await reserve_billing_operation(
        db,
        reservation_service=reservation_service,
        scope=scope,
        request=request,
    )


def build_storybook_settlement_inputs(
    *,
    scope: BillingScope,
    result: BillingResult[object],
) -> tuple[Decimal, Decimal, dict]:
    """Expand a billed storybook result into reservation settle inputs."""
    return build_billing_settlement_inputs(scope=scope, result=result)


async def run_storybook_sync_operation(
    *,
    reservation_service: CreditReservationService,
    scope: BillingScope,
    request: BillingReservationRequest,
    execute_fn: Callable[[], Awaitable[BillingResult[_T]]],
    release_reason: str = "operation_failed",
    settlement_error: str = "settle_exception",
    db_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] = get_db_session_local,
) -> _T:
    """Reserve, execute, then settle one storybook operation."""
    return await run_billed_operation(
        reservation_service=reservation_service,
        scope=scope,
        request=request,
        execute_fn=execute_fn,
        release_reason=release_reason,
        settlement_error=settlement_error,
        db_factory=db_factory,
    )


async def finalize_storybook_async_operation(
    *,
    reservation_service: CreditReservationService,
    scope: BillingScope,
    reservation_id: str,
    result: BillingResult[object] | None,
    release_reason: str,
    settlement_error: str = "settle_exception",
    db_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] = get_db_session_local,
) -> None:
    """Finalize one already-reserved async storybook operation."""
    await finalize_billing_operation(
        reservation_service=reservation_service,
        scope=scope,
        reservation_id=reservation_id,
        result=result,
        release_reason=release_reason,
        settlement_error=settlement_error,
        db_factory=db_factory,
    )
