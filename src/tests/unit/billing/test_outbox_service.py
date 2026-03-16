"""Tests for BillingUsageFactService: capture, process, and retry."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.billing.outbox.service import (
    BillingUsageFactService,
    _STATUS_CAPTURED,
    _STATUS_MANUAL_REVIEW,
    _STATUS_PROCESSED,
    _STATUS_PROCESSING,
    _MAX_ATTEMPTS,
)
from ii_agent.billing.reservations.types import BillingSettlementResult, ReservationStatus
from ii_agent.core.llm.token_record import TokenRecord

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeNestedTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


def _make_db():
    db = MagicMock()
    db.begin_nested.return_value = _FakeNestedTransaction()
    db.flush = AsyncMock()
    return db


def _make_hold(reservation_id="res-1"):
    return SimpleNamespace(
        reservation_id=reservation_id,
        idempotency_key=f"idem-{reservation_id}",
        reserved_credits=Decimal("5"),
        reserved_bonus_credits=Decimal("3"),
        quoted_usd=Decimal("0.12"),
        max_usd=Decimal("0.12"),
        output_token_cap=1024,
    )


def _make_reserved_llm_call(reservation_id="res-1"):
    from ii_agent.billing.credits.pricing import ModelPricing

    return SimpleNamespace(
        hold=_make_hold(reservation_id),
        input_tokens_estimate=100,
        output_token_cap=1024,
        pricing=ModelPricing.get_default_pricing("claude-sonnet-4-5"),
        provider_options=None,
    )


def _make_fact(
    *,
    id=1,
    reservation_id="res-1",
    user_id="user-1",
    event_kind="llm",
    status=_STATUS_CAPTURED,
    attempt_count=0,
    cost_usd=None,
    model_id="claude-sonnet-4-5",
    prompt_tokens=100,
    completion_tokens=50,
    cache_read_tokens=0,
    cache_write_tokens=0,
    reasoning_tokens=0,
):
    return SimpleNamespace(
        id=id,
        reservation_id=reservation_id,
        user_id=user_id,
        session_id="session-1",
        run_id=None,
        message_id=None,
        billing_kind="llm_usage",
        event_kind=event_kind,
        app_kind="chat",
        provider="anthropic",
        request_kind="chat_response",
        model_id=model_id,
        tool_name=None,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        reasoning_tokens=reasoning_tokens,
        latency_ms=200,
        cost_usd=Decimal(str(cost_usd)) if cost_usd else None,
        charged_credits=None,
        status=status,
        attempt_count=attempt_count,
        last_error=None,
        captured_at=datetime.now(timezone.utc),
        processing_started_at=None,
        last_enqueued_at=None,
        processed_at=None,
        failed_at=None,
    )


def _settled_result(reservation_id="res-1"):
    return BillingSettlementResult(
        reservation_id=reservation_id,
        status=ReservationStatus.SETTLED,
        charged_credits=Decimal("2"),
        charged_bonus_credits=Decimal("1"),
    )


def _failed_result(reservation_id="res-1"):
    return BillingSettlementResult(
        reservation_id=reservation_id,
        status=ReservationStatus.SETTLEMENT_FAILED,
    )


def _make_service(
    *,
    settle_result=None,
    settle_side_effect=None,
):
    fact_repo = MagicMock()
    fact_repo.insert_idempotent = AsyncMock()
    fact_repo.lock_by_id = AsyncMock()
    fact_repo.list_dispatchable_locked = AsyncMock(return_value=[])

    reservation_repo = MagicMock()
    reservation_repo.get_by_id = AsyncMock(
        return_value=SimpleNamespace(user_id="user-1", session_id="session-1")
    )

    reservation_service = MagicMock()
    reservation_service.settle = AsyncMock(
        return_value=settle_result or _settled_result(),
        side_effect=settle_side_effect,
    )
    reservation_service.mark_settlement_failed = AsyncMock()

    service = BillingUsageFactService(
        repository=fact_repo,
        reservation_repository=reservation_repo,
        reservation_service=reservation_service,
    )
    return service, fact_repo, reservation_service


# ---------------------------------------------------------------------------
# capture_llm_fact
# ---------------------------------------------------------------------------


class TestCaptureLLMFact:
    @pytest.mark.asyncio
    async def test_captures_fact_with_token_data(self):
        service, fact_repo, _ = _make_service()
        fact_repo.insert_idempotent.return_value = _make_fact()
        db = _make_db()

        reservation = _make_reserved_llm_call()
        token_record = TokenRecord(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=10,
            model_id="claude-sonnet-4-5",
        )
        result = await service.capture_llm_fact(
            db,
            reservation=reservation,
            user_id="user-1",
            session_id="session-1",
            run_id="run-1",
            app_kind="chat",
            provider="anthropic",
            request_kind="chat_response",
            token_record=token_record,
            latency_ms=200,
        )

        assert result is not None
        fact_repo.insert_idempotent.assert_awaited_once()
        kwargs = fact_repo.insert_idempotent.call_args.kwargs
        assert kwargs["reservation_id"] == "res-1"
        assert kwargs["prompt_tokens"] == 100
        assert kwargs["completion_tokens"] == 50
        assert kwargs["cache_read_tokens"] == 10
        assert kwargs["billing_kind"] == "llm_usage"
        assert kwargs["event_kind"] == "llm"

    @pytest.mark.asyncio
    async def test_returns_none_when_reservation_is_none(self):
        service, fact_repo, _ = _make_service()
        db = _make_db()

        result = await service.capture_llm_fact(
            db,
            reservation=None,
            user_id="user-1",
            session_id="session-1",
            run_id=None,
            app_kind="chat",
            provider="anthropic",
            request_kind="chat_response",
            token_record=TokenRecord(),
        )

        assert result is None
        fact_repo.insert_idempotent.assert_not_awaited()


# ---------------------------------------------------------------------------
# capture_tool_fact
# ---------------------------------------------------------------------------


class TestCaptureToolFact:
    @pytest.mark.asyncio
    async def test_captures_tool_fact_with_cost(self):
        service, fact_repo, _ = _make_service()
        fact_repo.insert_idempotent.return_value = _make_fact(event_kind="tool")
        db = _make_db()

        result = await service.capture_tool_fact(
            db,
            reservation_id="res-tool-1",
            user_id="user-1",
            session_id="session-1",
            run_id=None,
            app_kind="chat",
            tool_name="generate_image",
            provider="openai",
            actual_cost_usd=0.04,
            latency_ms=500,
        )

        assert result is not None
        kwargs = fact_repo.insert_idempotent.call_args.kwargs
        assert kwargs["reservation_id"] == "res-tool-1"
        assert kwargs["billing_kind"] == "tool_usage"
        assert kwargs["event_kind"] == "tool"
        assert kwargs["tool_name"] == "generate_image"
        assert float(kwargs["cost_usd"]) == pytest.approx(0.04)

    @pytest.mark.asyncio
    async def test_negative_cost_is_clamped_to_zero(self):
        service, fact_repo, _ = _make_service()
        fact_repo.insert_idempotent.return_value = _make_fact(event_kind="tool", cost_usd=0)
        db = _make_db()

        await service.capture_tool_fact(
            db,
            reservation_id="res-tool-2",
            user_id="user-1",
            session_id="session-1",
            run_id=None,
            app_kind="chat",
            tool_name="web_search",
            provider="google",
            actual_cost_usd=-0.01,
        )

        kwargs = fact_repo.insert_idempotent.call_args.kwargs
        assert float(kwargs["cost_usd"]) == 0.0


# ---------------------------------------------------------------------------
# process_fact
# ---------------------------------------------------------------------------


class TestProcessFact:
    @pytest.mark.asyncio
    async def test_process_fact_settles_and_marks_processed(self):
        service, fact_repo, reservation_service = _make_service()
        fact = _make_fact()
        fact_repo.lock_by_id.return_value = fact
        db = _make_db()

        result = await service.process_fact(db, fact_id=1)

        assert result is not None
        assert result.status == ReservationStatus.SETTLED
        reservation_service.settle.assert_awaited_once()
        assert fact.status == _STATUS_PROCESSED
        assert fact.charged_credits is not None
        assert fact.processed_at is not None

    @pytest.mark.asyncio
    async def test_process_fact_returns_none_when_not_found(self):
        service, fact_repo, _ = _make_service()
        fact_repo.lock_by_id.return_value = None
        db = _make_db()

        result = await service.process_fact(db, fact_id=999)

        assert result is None

    @pytest.mark.asyncio
    async def test_process_fact_marks_manual_review_after_max_attempts(self):
        service, fact_repo, reservation_service = _make_service(
            settle_side_effect=RuntimeError("db error"),
        )
        fact = _make_fact(attempt_count=_MAX_ATTEMPTS - 1)
        fact_repo.lock_by_id.return_value = fact
        db = _make_db()

        with pytest.raises(RuntimeError):
            await service.process_fact(db, fact_id=1)

        assert fact.status == _STATUS_MANUAL_REVIEW
        assert fact.last_error == "db error"
        reservation_service.mark_settlement_failed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_fact_retries_on_failure_below_max(self):
        service, fact_repo, reservation_service = _make_service(
            settle_side_effect=RuntimeError("transient"),
        )
        fact = _make_fact(attempt_count=0)
        fact_repo.lock_by_id.return_value = fact
        db = _make_db()

        with pytest.raises(RuntimeError):
            await service.process_fact(db, fact_id=1)

        # Requeued for retry, not manual_review
        assert fact.status == _STATUS_CAPTURED
        assert fact.attempt_count == 1
        assert fact.last_error == "transient"

    @pytest.mark.asyncio
    async def test_process_fact_handles_settlement_failed_result(self):
        service, fact_repo, _ = _make_service(settle_result=_failed_result())
        fact = _make_fact(attempt_count=0)
        fact_repo.lock_by_id.return_value = fact
        db = _make_db()

        result = await service.process_fact(db, fact_id=1)

        assert result.status == ReservationStatus.SETTLEMENT_FAILED
        assert fact.status == _STATUS_CAPTURED  # requeued for retry
        assert fact.last_error == "settlement_failed"

    @pytest.mark.asyncio
    async def test_process_already_processed_fact_is_noop(self):
        service, fact_repo, reservation_service = _make_service()
        fact = _make_fact(status=_STATUS_PROCESSED)
        fact_repo.lock_by_id.return_value = fact
        db = _make_db()

        result = await service.process_fact(db, fact_id=1)

        # Should still call settle (idempotent) but won't change status
        assert result is not None

    @pytest.mark.asyncio
    async def test_process_manual_review_fact_returns_none(self):
        service, fact_repo, reservation_service = _make_service()
        fact = _make_fact(status=_STATUS_MANUAL_REVIEW)
        fact_repo.lock_by_id.return_value = fact
        db = _make_db()

        result = await service.process_fact(db, fact_id=1)

        assert result is None
        reservation_service.settle.assert_not_awaited()


# ---------------------------------------------------------------------------
# retry_dispatchable
# ---------------------------------------------------------------------------


class TestRetryDispatchable:
    @pytest.mark.asyncio
    async def test_processes_captured_facts(self):
        service, fact_repo, reservation_service = _make_service()
        facts = [_make_fact(id=i) for i in range(3)]
        fact_repo.list_dispatchable_locked.return_value = facts
        db = _make_db()

        count = await service.retry_dispatchable(db, limit=10)

        assert count == 3
        assert reservation_service.settle.await_count == 3
        for fact in facts:
            assert fact.status == _STATUS_PROCESSED

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_dispatchable_facts(self):
        service, fact_repo, _ = _make_service()
        fact_repo.list_dispatchable_locked.return_value = []
        db = _make_db()

        count = await service.retry_dispatchable(db, limit=10)

        assert count == 0

    @pytest.mark.asyncio
    async def test_continues_processing_after_individual_failure(self):
        """One fact failing should not prevent processing subsequent facts."""
        service, fact_repo, reservation_service = _make_service()

        good_fact = _make_fact(id=1)
        bad_fact = _make_fact(id=2)
        good_fact2 = _make_fact(id=3)

        # Make settle fail only for fact id=2
        call_count = 0
        original_settled = _settled_result()

        async def _settle_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("transient error")
            return original_settled

        reservation_service.settle = AsyncMock(side_effect=_settle_side_effect)

        fact_repo.list_dispatchable_locked.return_value = [good_fact, bad_fact, good_fact2]
        db = _make_db()

        count = await service.retry_dispatchable(db, limit=10)

        assert count == 3  # all 3 attempted
        assert good_fact.status == _STATUS_PROCESSED
        assert bad_fact.status == _STATUS_CAPTURED  # requeued
        assert good_fact2.status == _STATUS_PROCESSED


# ---------------------------------------------------------------------------
# idempotency_key required on reserve
# ---------------------------------------------------------------------------


class TestIdempotencyKeyRequired:
    @pytest.mark.asyncio
    async def test_reserve_rejects_none_idempotency_key(self):
        from ii_agent.billing.reservations.service import CreditReservationService
        from ii_agent.billing.reservations.types import BillingQuote

        service = CreditReservationService(
            balance_repo=MagicMock(),
            ledger_repo=MagicMock(),
            reservation_repo=MagicMock(),
            credit_service=MagicMock(),
            usage_service=MagicMock(),
        )
        db = _make_db()

        with pytest.raises(ValueError, match="idempotency_key is required"):
            await service.reserve(
                db,
                user_id="user-1",
                source_domain="chat_llm",
                source_id="call-1",
                billing_kind="llm_usage",
                quote=BillingQuote(
                    strategy="bounded",
                    reserve_usd=Decimal("0.075"),
                    max_usd=Decimal("0.075"),
                ),
                idempotency_key="",  # empty string
            )

    @pytest.mark.asyncio
    async def test_reserve_rejects_empty_string_idempotency_key(self):
        from ii_agent.billing.reservations.service import CreditReservationService
        from ii_agent.billing.reservations.types import BillingQuote

        service = CreditReservationService(
            balance_repo=MagicMock(),
            ledger_repo=MagicMock(),
            reservation_repo=MagicMock(),
            credit_service=MagicMock(),
            usage_service=MagicMock(),
        )
        db = _make_db()

        with pytest.raises(ValueError, match="idempotency_key is required"):
            await service.reserve(
                db,
                user_id="user-1",
                source_domain="chat_llm",
                source_id="call-1",
                billing_kind="llm_usage",
                quote=BillingQuote(
                    strategy="bounded",
                    reserve_usd=Decimal("0.075"),
                    max_usd=Decimal("0.075"),
                ),
                idempotency_key="",
            )
