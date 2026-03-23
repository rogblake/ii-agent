from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ii_agent.billing.exceptions import BillingDuplicateOperationError
from ii_agent.billing.operations import (
    finalize_billing_operation,
    reserve_billing_operation,
    run_billed_operation,
)
from ii_agent.billing.types import (
    BillingContextValue,
    BillingReservationRequest,
    BillingScope,
)
from ii_agent.billing.reservations.types import (
    BillingKind,
    BillingQuote,
    ReservationHold,
    ReservationStatus,
)


class _ReservationServiceStub:
    def __init__(self, hold: ReservationHold) -> None:
        self._hold = hold
        self.release = AsyncMock()
        self.capture_settlement_input = AsyncMock()
        self.settle = AsyncMock()
        self.mark_settlement_failed = AsyncMock()

    async def reserve(self, db, **kwargs):  # noqa: ANN001
        return self._hold


def _build_scope() -> BillingScope:
    return BillingScope.for_session(
        user_id="user-1",
        app_kind="chat",
        session_id="session-1",
        billing_context=BillingContextValue.STORYBOOK,
        run_id="run-1",
    )


def _build_request() -> BillingReservationRequest:
    return BillingReservationRequest(
        source_domain="voice_generation",
        source_id="voice:storybook-1:req-1",
        billing_kind=BillingKind.TOOL_USAGE,
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.02"),
            max_usd=Decimal("0.02"),
        ),
        tool_name="storybook_voiceover",
        idempotency_key=(
            "voice_generation:chat:storybook:session:session-1:run-1:voice:storybook-1:req-1"
        ),
        metadata={"storybook_id": "storybook-1"},
    )


def _duplicate_hold() -> ReservationHold:
    return ReservationHold(
        reservation_id="res-duplicate",
        idempotency_key="voice-key",
        reserved_credits=Decimal("1"),
        reserved_bonus_credits=Decimal("0"),
        quoted_usd=Decimal("0.02"),
        max_usd=Decimal("0.02"),
        status=ReservationStatus.RESERVED,
        was_created=False,
    )


@asynccontextmanager
async def _fake_db_factory():
    yield SimpleNamespace(commit=AsyncMock())


@pytest.mark.asyncio
async def test_reserve_billing_operation_rejects_duplicate_hold() -> None:
    reservation_service = _ReservationServiceStub(_duplicate_hold())

    with pytest.raises(BillingDuplicateOperationError, match="already in progress"):
        await reserve_billing_operation(
            object(),
            reservation_service=reservation_service,
            scope=_build_scope(),
            request=_build_request(),
        )


@pytest.mark.asyncio
async def test_run_billed_operation_does_not_execute_duplicate_work() -> None:
    reservation_service = _ReservationServiceStub(_duplicate_hold())
    execute_fn = AsyncMock()

    with pytest.raises(BillingDuplicateOperationError, match="already in progress"):
        await run_billed_operation(
            reservation_service=reservation_service,
            scope=_build_scope(),
            request=_build_request(),
            execute_fn=execute_fn,
            db_factory=_fake_db_factory,
        )

    execute_fn.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalize_billing_operation_releases_when_result_is_missing() -> None:
    reservation_service = _ReservationServiceStub(_duplicate_hold())

    await finalize_billing_operation(
        reservation_service=reservation_service,
        scope=_build_scope(),
        reservation_id="res-missing",
        result=None,
        release_reason="operation_failed",
        db_factory=_fake_db_factory,
    )

    reservation_service.release.assert_awaited_once()
    reservation_service.capture_settlement_input.assert_not_awaited()
    reservation_service.settle.assert_not_awaited()
