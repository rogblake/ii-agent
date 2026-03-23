"""Reusable helpers for reserve -> capture -> settle billing flows."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from decimal import Decimal
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.credits.utils import usd_to_credits
from ii_agent.billing.types import BillingReservationRequest, BillingResult, BillingScope
from ii_agent.billing.reservations.service import CreditReservationService
from ii_agent.billing.reservations.types import (
    BillingSettlementResult,
    ReservationHold,
    raise_if_duplicate_operation,
)
from ii_agent.core.db.manager import get_db_session_local

_T = TypeVar("_T")


async def reserve_billing_operation(
    db: AsyncSession,
    *,
    reservation_service: CreditReservationService,
    scope: BillingScope,
    request: BillingReservationRequest,
) -> ReservationHold | None:
    """Create one reservation using the shared billing scope metadata."""
    if request.quote is None:
        return None

    hold = await reservation_service.reserve(db, **build_billing_reservation_kwargs(scope, request))
    raise_if_duplicate_operation(hold)
    return hold


def build_billing_reservation_kwargs(
    scope: BillingScope,
    request: BillingReservationRequest,
) -> dict[str, Any]:
    """Build canonical reservation kwargs from shared scope + request inputs."""
    return {
        "user_id": scope.user_id,
        "billing_context": scope.billing_context,
        "subject_kind": scope.subject.kind.value,
        "subject_id": scope.subject.id,
        "run_id": str(scope.run_id) if scope.run_id is not None else None,
        "source_domain": request.source_domain,
        "source_id": request.source_id,
        "billing_kind": request.billing_kind,
        "quote": request.quote,
        "model_id": request.model_id,
        "tool_name": request.tool_name,
        "idempotency_key": request.idempotency_key,
        "metadata": {
            **scope.billing_metadata(),
            **request.metadata,
        },
        "output_token_cap": request.output_token_cap,
    }


def build_billing_settlement_inputs(
    *,
    scope: BillingScope,
    result: BillingResult[object],
) -> tuple[Decimal, Decimal, dict[str, Any]]:
    """Expand a billed result into reservation settle inputs."""
    actual_usd = Decimal(str(result.actual_usd))
    actual_credits = (
        Decimal(str(result.actual_credits))
        if result.actual_credits is not None
        else usd_to_credits(actual_usd)
    )
    usage_payload = {
        **scope.billing_metadata(),
        **result.usage_payload,
    }
    return actual_usd, actual_credits, usage_payload


async def capture_billing_result(
    db: AsyncSession,
    *,
    reservation_service: CreditReservationService,
    scope: BillingScope,
    reservation_id: str,
    result: BillingResult[object],
) -> tuple[Decimal, Decimal, dict[str, Any]]:
    """Persist exact settlement inputs so failed settles can be replayed."""
    actual_usd, actual_credits, usage_payload = build_billing_settlement_inputs(
        scope=scope,
        result=result,
    )
    await reservation_service.capture_settlement_input(
        db,
        reservation_id=reservation_id,
        actual_credits=actual_credits,
        actual_usd=actual_usd,
        usage_payload=usage_payload,
    )
    return actual_usd, actual_credits, usage_payload


async def settle_billing_result(
    db: AsyncSession,
    *,
    reservation_service: CreditReservationService,
    scope: BillingScope,
    reservation_id: str,
    result: BillingResult[object],
) -> BillingSettlementResult:
    """Settle a reservation from a generic billed result payload."""
    actual_usd, actual_credits, usage_payload = build_billing_settlement_inputs(
        scope=scope,
        result=result,
    )
    return await reservation_service.settle(
        db,
        reservation_id=reservation_id,
        actual_credits=actual_credits,
        actual_usd=actual_usd,
        usage_payload=usage_payload,
    )


async def finalize_billing_operation(
    *,
    reservation_service: CreditReservationService,
    scope: BillingScope,
    reservation_id: str,
    result: BillingResult[object] | None,
    release_reason: str,
    settlement_error: str = "settle_exception",
    db_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] = get_db_session_local,
) -> None:
    """Finalize a previously reserved async billing operation."""
    if result is None:
        async with db_factory() as release_db:
            await reservation_service.release(
                release_db,
                reservation_id=reservation_id,
                reason=release_reason,
            )
            await release_db.commit()
        return

    try:
        async with db_factory() as capture_db:
            await capture_billing_result(
                capture_db,
                reservation_service=reservation_service,
                scope=scope,
                reservation_id=reservation_id,
                result=result,
            )
            await capture_db.commit()

        async with db_factory() as settle_db:
            await settle_billing_result(
                settle_db,
                reservation_service=reservation_service,
                scope=scope,
                reservation_id=reservation_id,
                result=result,
            )
            await settle_db.commit()
    except Exception:
        async with db_factory() as failed_db:
            await reservation_service.mark_settlement_failed(
                failed_db,
                reservation_id=reservation_id,
                error=settlement_error,
            )
            await failed_db.commit()
        raise


async def run_billed_operation(
    *,
    reservation_service: CreditReservationService,
    scope: BillingScope,
    request: BillingReservationRequest,
    execute_fn: Callable[[], Awaitable[BillingResult[_T]]],
    release_reason: str = "operation_failed",
    settlement_error: str = "settle_exception",
    db_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] = get_db_session_local,
) -> _T:
    """Reserve, execute, then settle one billed async operation."""
    async with db_factory() as reserve_db:
        reservation = await reserve_billing_operation(
            reserve_db,
            reservation_service=reservation_service,
            scope=scope,
            request=request,
        )
        await reserve_db.commit()

    try:
        result = await execute_fn()
    except Exception:
        if reservation is not None:
            async with db_factory() as release_db:
                await reservation_service.release(
                    release_db,
                    reservation_id=reservation.reservation_id,
                    reason=release_reason,
                )
                await release_db.commit()
        raise

    if reservation is None:
        return result.value

    await finalize_billing_operation(
        reservation_service=reservation_service,
        scope=scope,
        reservation_id=reservation.reservation_id,
        result=result,
        release_reason=release_reason,
        settlement_error=settlement_error,
        db_factory=db_factory,
    )
    return result.value
