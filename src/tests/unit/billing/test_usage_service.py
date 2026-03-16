"""Unit tests for UsageService covering session usage tracking."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.billing.credits.service import CreditDeductionResult
from ii_agent.billing.usage.service import UsageService

pytestmark = pytest.mark.unit

_USER_ID = str(uuid.uuid4())


class FakeCreditService:
    def __init__(self, *, deduct_result: object = True):
        self._deduct_result = deduct_result
        self.deduct_calls: list[dict] = []

    async def deduct(self, db, user_id, amount, **kwargs):
        self.deduct_calls.append(
            {"user_id": user_id, "amount": amount, **kwargs}
        )
        return self._deduct_result


class FakeMetricsRepo:
    def __init__(self):
        self.records = {}

    async def get_by_session_id(self, db, session_id):
        return self.records.get(session_id)

    async def create(self, db, session_id, credits):
        record = SimpleNamespace(
            session_id=session_id,
            credits=credits,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.records[session_id] = record
        return record


class FakeUsageRecordRepo:
    def __init__(self):
        self.create_calls: list[dict] = []

    async def create(self, db, **kwargs):
        self.create_calls.append(kwargs)
        return SimpleNamespace(id=len(self.create_calls), **kwargs)


def _make_service(
    credit_service=None, metrics_repo=None, usage_record_repo=None
) -> UsageService:
    return UsageService(
        credit_service=credit_service or FakeCreditService(),
        metrics_repo=metrics_repo or FakeMetricsRepo(),
        usage_record_repo=usage_record_repo,
    )


def _make_fake_db():
    """Return a fake async db session."""
    db = AsyncMock()
    db.bind.dialect.name = "postgresql"
    return db


# ---------------------------------------------------------------------------
# Tests – deduct_and_track_session_usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deduct_and_track_zero_amount_returns_true():
    """amount <= 0 is a no-op and returns True."""
    svc = _make_service()

    result = await svc.deduct_and_track_session_usage(
        None, user_id=_USER_ID, session_id="sess-1", amount=0.0
    )

    assert result is True


@pytest.mark.asyncio
async def test_deduct_and_track_negative_amount_returns_true():
    """Negative amount is treated as no-op."""
    svc = _make_service()

    result = await svc.deduct_and_track_session_usage(
        None, user_id=_USER_ID, session_id="sess-1", amount=-5.0
    )

    assert result is True


@pytest.mark.asyncio
async def test_deduct_and_track_success_accumulates():
    """Successful deduction calls accumulate_session_usage via db.execute."""
    svc = _make_service()
    db = _make_fake_db()

    result = await svc.deduct_and_track_session_usage(
        db, user_id=_USER_ID, session_id="sess-1", amount=2.0
    )

    assert result is True
    # Verify the upsert was executed (deduct call + accumulate call)
    db.execute.assert_called()
    db.flush.assert_called()


@pytest.mark.asyncio
async def test_deduct_and_track_dual_writes_usage_record():
    """Successful deductions create one usage_records row when repo is configured."""
    usage_record_repo = FakeUsageRecordRepo()
    credit_service = FakeCreditService(
        deduct_result=CreditDeductionResult(
            ledger_entry_id=42,
            charged_credits=Decimal("-1.25"),
            charged_bonus_credits=Decimal("-0.75"),
        )
    )
    svc = _make_service(
        credit_service=credit_service,
        usage_record_repo=usage_record_repo,
    )
    db = _make_fake_db()
    run_id = str(uuid.uuid4())

    result = await svc.deduct_and_track_session_usage(
        db,
        user_id=_USER_ID,
        session_id="sess-1",
        amount=2.0,
        model_id="claude-sonnet-4-5",
        source_domain="llm_usage",
        entry_metadata={
            "run_id": run_id,
            "billing_kind": "llm_usage",
            "app_kind": "chat",
            "provider": "anthropic",
            "input_tokens": 11,
            "output_tokens": 7,
            "cache_read_tokens": 3,
            "cache_write_tokens": 2,
            "reasoning_tokens": 5,
            "latency_ms": 1200,
            "direct_cost_usd": 0.125,
        },
    )

    assert result is True
    assert len(usage_record_repo.create_calls) == 1
    call = usage_record_repo.create_calls[0]
    assert call["ledger_entry_id"] == 42
    assert call["run_id"] == run_id
    assert call["billing_kind"] == "llm_usage"
    assert call["app_kind"] == "chat"
    assert call["provider"] == "anthropic"
    assert call["input_tokens"] == 11
    assert call["output_tokens"] == 7
    assert call["cache_read_tokens"] == 3
    assert call["cache_write_tokens"] == 2
    assert call["reasoning_tokens"] == 5
    assert call["latency_ms"] == 1200
    assert call["cost_usd"] == 0.125
    assert call["credits_charged"] == Decimal("2.00")


@pytest.mark.asyncio
async def test_deduct_and_track_skips_usage_record_on_duplicate():
    """Duplicate idempotent deductions do not create usage_records rows."""
    usage_record_repo = FakeUsageRecordRepo()
    credit_service = FakeCreditService(deduct_result=None)
    svc = _make_service(
        credit_service=credit_service,
        usage_record_repo=usage_record_repo,
    )
    db = _make_fake_db()

    result = await svc.deduct_and_track_session_usage(
        db,
        user_id=_USER_ID,
        session_id="sess-1",
        amount=5.0,
    )

    assert result is True
    assert usage_record_repo.create_calls == []


@pytest.mark.asyncio
async def test_deduct_and_track_returns_false_when_insufficient():
    """Returns False when deduction fails (insufficient balance)."""
    credit_service = FakeCreditService(deduct_result=False)
    svc = _make_service(credit_service=credit_service)

    result = await svc.deduct_and_track_session_usage(
        None, user_id=_USER_ID, session_id="sess-1", amount=5.0
    )

    assert result is False


# ---------------------------------------------------------------------------
# Tests – accumulate_session_usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_settled_usage_dual_writes_usage_record_and_session_metrics():
    usage_record_repo = FakeUsageRecordRepo()
    svc = _make_service(usage_record_repo=usage_record_repo)
    db = _make_fake_db()

    record_id = await svc.record_settled_usage(
        db,
        user_id=_USER_ID,
        session_id="sess-1",
        run_id="run-1",
        amount=1.5,
        source_domain="chat_llm",
        billing_kind="llm_usage",
        ledger_entry_id=123,
        model_id="gpt-4o",
        provider="openai",
        input_tokens=42,
        output_tokens=7,
        cost_usd=0.0225,
        app_kind="chat",
        usage_metadata={"reservation_id": "reservation-1"},
    )

    assert record_id is not None
    assert len(usage_record_repo.create_calls) == 1
    call = usage_record_repo.create_calls[0]
    assert call["ledger_entry_id"] == 123
    assert call["credits_charged"] == Decimal("1.5")
    assert call["model_id"] == "gpt-4o"
    db.execute.assert_called()
    db.flush.assert_called()


@pytest.mark.asyncio
async def test_accumulate_session_usage_executes_upsert():
    """Executes INSERT ... ON CONFLICT DO UPDATE via db.execute."""
    svc = _make_service()
    db = _make_fake_db()

    await svc.accumulate_session_usage(db, "new-session", -1.5)

    db.execute.assert_called_once()
    db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_accumulate_session_usage_multiple_calls():
    """Multiple accumulations each execute the upsert statement."""
    svc = _make_service()
    db = _make_fake_db()

    await svc.accumulate_session_usage(db, "session-1", -1.0)
    await svc.accumulate_session_usage(db, "session-1", -2.5)

    assert db.execute.call_count == 2
    assert db.flush.call_count == 2


@pytest.mark.asyncio
async def test_accumulate_session_usage_raises_on_error():
    """Propagates exceptions from db execution."""
    svc = _make_service()
    db = _make_fake_db()
    db.execute = AsyncMock(side_effect=Exception("DB error"))

    with pytest.raises(Exception, match="DB error"):
        await svc.accumulate_session_usage(db, "sess", -1.0)


# ---------------------------------------------------------------------------
# Tests – get_session_usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_session_usage_returns_dict_when_found():
    """Returns usage dict when record exists."""
    metrics_repo = FakeMetricsRepo()
    await metrics_repo.create(None, "sess-1", -3.0)
    svc = _make_service(metrics_repo=metrics_repo)

    result = await svc.get_session_usage(None, "sess-1")

    assert result is not None
    assert result["session_id"] == "sess-1"
    assert result["credits"] == -3.0


@pytest.mark.asyncio
async def test_get_session_usage_returns_none_when_not_found():
    """Returns None when no record for session."""
    svc = _make_service()

    result = await svc.get_session_usage(None, "nonexistent")

    assert result is None


@pytest.mark.asyncio
async def test_get_session_usage_raises_on_error():
    """Propagates exceptions from metrics repo."""
    metrics_repo = MagicMock()
    metrics_repo.get_by_session_id = AsyncMock(side_effect=RuntimeError("DB crash"))
    svc = _make_service(metrics_repo=metrics_repo)

    with pytest.raises(RuntimeError):
        await svc.get_session_usage(None, "sess")


# ---------------------------------------------------------------------------
# Tests – deduct_and_track metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deduct_and_track_passes_model_id_metadata():
    """model_id is included in entry_metadata passed to credit_service.deduct."""
    credit_service = FakeCreditService()
    svc = _make_service(credit_service=credit_service)
    db = _make_fake_db()

    await svc.deduct_and_track_session_usage(
        db,
        user_id=_USER_ID,
        session_id="sess-1",
        amount=2.0,
        model_id="claude-sonnet-4-5",
    )

    call = credit_service.deduct_calls[0]
    assert call["entry_metadata"]["model_id"] == "claude-sonnet-4-5"
    assert call["entry_metadata"]["session_id"] == "sess-1"


@pytest.mark.asyncio
async def test_deduct_and_track_no_model_id_metadata():
    """When model_id is None, entry_metadata only has session_id."""
    credit_service = FakeCreditService()
    svc = _make_service(credit_service=credit_service)
    db = _make_fake_db()

    await svc.deduct_and_track_session_usage(
        db,
        user_id=_USER_ID,
        session_id="sess-1",
        amount=2.0,
    )

    call = credit_service.deduct_calls[0]
    assert "model_id" not in call["entry_metadata"]
    assert call["entry_metadata"]["session_id"] == "sess-1"


@pytest.mark.asyncio
async def test_deduct_and_track_passes_idempotency_key():
    """idempotency_key is forwarded to credit_service.deduct."""
    credit_service = FakeCreditService()
    svc = _make_service(credit_service=credit_service)
    db = _make_fake_db()

    await svc.deduct_and_track_session_usage(
        db,
        user_id=_USER_ID,
        session_id="sess-1",
        amount=2.0,
        idempotency_key="idem-123",
    )

    call = credit_service.deduct_calls[0]
    assert call["idempotency_key"] == "idem-123"


@pytest.mark.asyncio
async def test_deduct_and_track_does_not_accumulate_on_failure():
    """When deduction fails, session usage is NOT accumulated."""
    credit_service = FakeCreditService(deduct_result=False)
    svc = _make_service(credit_service=credit_service)
    db = _make_fake_db()

    result = await svc.deduct_and_track_session_usage(
        db,
        user_id=_USER_ID,
        session_id="sess-1",
        amount=999.0,
    )

    assert result is False
    # accumulate_session_usage uses db.execute — should NOT have been called
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_deduct_and_track_does_not_accumulate_on_duplicate():
    """When deduction returns None (idempotent duplicate), session usage is NOT accumulated."""
    credit_service = FakeCreditService(deduct_result=None)
    svc = _make_service(credit_service=credit_service)
    db = _make_fake_db()

    result = await svc.deduct_and_track_session_usage(
        db,
        user_id=_USER_ID,
        session_id="sess-1",
        amount=5.0,
    )

    assert result is True
    # accumulate_session_usage uses db.execute — should NOT have been called
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_deduct_and_track_passes_source_domain():
    """source_domain is forwarded to credit_service.deduct."""
    credit_service = FakeCreditService()
    svc = _make_service(credit_service=credit_service)
    db = _make_fake_db()

    await svc.deduct_and_track_session_usage(
        db,
        user_id=_USER_ID,
        session_id="sess-1",
        amount=2.0,
        source_domain="voice_generation",
    )

    call = credit_service.deduct_calls[0]
    assert call["source_domain"] == "voice_generation"
