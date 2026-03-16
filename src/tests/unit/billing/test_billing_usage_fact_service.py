"""Unit tests for durable billing usage facts."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.billing.outbox.service import BillingUsageFactService
from ii_agent.billing.reservations.types import BillingSettlementResult, ReservationStatus
from ii_agent.core.llm.token_record import TokenRecord


class FakeFactRepository:
    def __init__(self):
        self.fact = None
        self.insert_calls: list[dict] = []

    async def insert_idempotent(self, db, **kwargs):
        self.insert_calls.append(kwargs)
        self.fact = SimpleNamespace(
            id=1,
            reservation_id=kwargs["reservation_id"],
            event_kind=kwargs["event_kind"],
            app_kind=kwargs.get("app_kind"),
            provider=kwargs.get("provider"),
            request_kind=kwargs.get("request_kind"),
            model_id=kwargs.get("model_id"),
            tool_name=kwargs.get("tool_name"),
            prompt_tokens=kwargs.get("prompt_tokens", 0),
            completion_tokens=kwargs.get("completion_tokens", 0),
            cache_read_tokens=kwargs.get("cache_read_tokens", 0),
            cache_write_tokens=kwargs.get("cache_write_tokens", 0),
            reasoning_tokens=kwargs.get("reasoning_tokens", 0),
            latency_ms=kwargs.get("latency_ms"),
            cost_usd=kwargs.get("cost_usd"),
            run_id=kwargs.get("run_id"),
            status="captured",
            attempt_count=0,
            charged_credits=None,
            processed_at=None,
            processing_started_at=None,
            failed_at=None,
            last_error=None,
        )
        return self.fact

    async def lock_by_id(self, db, fact_id):
        return self.fact

    async def list_dispatchable_locked(self, db, *, stale_before, limit):
        return [self.fact] if self.fact is not None else []


class FakeReservationRepository:
    def __init__(self):
        self.reservation = SimpleNamespace(
            id="res-1",
            user_id="user-1",
            session_id="session-1",
        )

    async def get_by_id(self, db, reservation_id):
        assert reservation_id == "res-1"
        return self.reservation


class FakeReservationService:
    def __init__(self, *, settle_result=None, settle_error: Exception | None = None):
        self.settle = AsyncMock(
            side_effect=settle_error if settle_error is not None else None,
            return_value=settle_result,
        )
        self.mark_settlement_failed = AsyncMock()


def _make_db():
    db = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_capture_tool_fact_resolves_user_context_from_reservation():
    repo = FakeFactRepository()
    reservation_repo = FakeReservationRepository()
    reservation_service = FakeReservationService()
    service = BillingUsageFactService(
        repository=repo,
        reservation_repository=reservation_repo,
        reservation_service=reservation_service,
    )

    await service.capture_tool_fact(
        _make_db(),
        reservation_id="res-1",
        user_id=None,
        session_id=None,
        run_id="00000000-0000-0000-0000-000000000001",
        app_kind="chat",
        tool_name="generate_image",
        provider="openai",
        actual_cost_usd=0.25,
    )

    assert repo.insert_calls[0]["user_id"] == "user-1"
    assert repo.insert_calls[0]["session_id"] == "session-1"


@pytest.mark.asyncio
async def test_process_fact_marks_processed_after_successful_settlement():
    repo = FakeFactRepository()
    reservation_repo = FakeReservationRepository()
    result = BillingSettlementResult(
        reservation_id="res-1",
        status=ReservationStatus.SETTLED,
        charged_credits=Decimal("1.5"),
    )
    reservation_service = FakeReservationService(settle_result=result)
    service = BillingUsageFactService(
        repository=repo,
        reservation_repository=reservation_repo,
        reservation_service=reservation_service,
    )
    await service.capture_llm_fact(
        _make_db(),
        reservation=SimpleNamespace(
            hold=SimpleNamespace(reservation_id="res-1"),
            pricing=SimpleNamespace(model_id="claude-sonnet-4-5"),
        ),
        user_id="user-1",
        session_id="session-1",
        run_id="00000000-0000-0000-0000-000000000001",
        app_kind="chat",
        provider="anthropic",
        request_kind="chat_response",
        token_record=TokenRecord(
            input_tokens=10,
            output_tokens=5,
            model_id="claude-sonnet-4-5",
        ),
        latency_ms=12,
    )
    db = _make_db()

    processed = await service.process_fact(db, fact_id=1)

    assert processed == result
    assert repo.fact.status == "processed"
    assert repo.fact.charged_credits == Decimal("1.5")
    reservation_service.settle.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_fact_marks_retryable_and_reservation_failed_on_exception():
    repo = FakeFactRepository()
    reservation_repo = FakeReservationRepository()
    reservation_service = FakeReservationService(settle_error=RuntimeError("boom"))
    service = BillingUsageFactService(
        repository=repo,
        reservation_repository=reservation_repo,
        reservation_service=reservation_service,
    )
    await service.capture_tool_fact(
        _make_db(),
        reservation_id="res-1",
        user_id="user-1",
        session_id="session-1",
        run_id=None,
        app_kind="chat",
        tool_name="generate_image",
        provider="openai",
        actual_cost_usd=0.25,
    )
    db = _make_db()

    with pytest.raises(RuntimeError, match="boom"):
        await service.process_fact(db, fact_id=1)

    assert repo.fact.status == "captured"
    assert repo.fact.last_error == "boom"
    reservation_service.mark_settlement_failed.assert_awaited_once_with(
        db,
        reservation_id="res-1",
        error="boom",
    )


@pytest.mark.asyncio
async def test_process_fact_keeps_failed_settlement_retryable():
    repo = FakeFactRepository()
    reservation_repo = FakeReservationRepository()
    result = BillingSettlementResult(
        reservation_id="res-1",
        status=ReservationStatus.SETTLEMENT_FAILED,
        charged_credits=Decimal("1.0"),
    )
    reservation_service = FakeReservationService(settle_result=result)
    service = BillingUsageFactService(
        repository=repo,
        reservation_repository=reservation_repo,
        reservation_service=reservation_service,
    )
    await service.capture_tool_fact(
        _make_db(),
        reservation_id="res-1",
        user_id="user-1",
        session_id="session-1",
        run_id=None,
        app_kind="chat",
        tool_name="generate_image",
        provider="openai",
        actual_cost_usd=0.25,
    )
    db = _make_db()

    processed = await service.process_fact(db, fact_id=1)

    assert processed == result
    assert repo.fact.status == "captured"
    assert repo.fact.charged_credits is None
    assert repo.fact.last_error == "settlement_failed"
