"""Unit tests for UsageService covering session usage tracking."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.billing.types import SubjectKind
from ii_agent.billing.usage.service import UsageService

pytestmark = pytest.mark.unit

_USER_ID = str(uuid.uuid4())


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


def _make_service(credit_service=None, metrics_repo=None, usage_record_repo=None) -> UsageService:
    return UsageService(
        credit_service=credit_service or MagicMock(),
        metrics_repo=metrics_repo or FakeMetricsRepo(),
        usage_record_repo=usage_record_repo,
    )


def _make_fake_db():
    """Return a fake async db session."""
    db = AsyncMock()
    db.bind.dialect.name = "postgresql"
    return db


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
        billing_context="chatloop",
        subject_kind="session",
        subject_id="sess-1",
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
    assert call["billing_context"] == "chatloop"
    assert call["subject_kind"] == "session"
    assert call["subject_id"] == "sess-1"
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


@pytest.mark.asyncio
async def test_record_settled_usage_skips_session_accumulation_for_non_session_subject():
    usage_record_repo = FakeUsageRecordRepo()
    svc = _make_service(usage_record_repo=usage_record_repo)
    db = _make_fake_db()

    record_id = await svc.record_settled_usage(
        db,
        user_id=_USER_ID,
        billing_context="enhanceprompt",
        subject_kind=SubjectKind.USER.value,
        subject_id="user-subject-1",
        run_id="run-1",
        amount=1.5,
        source_domain="chat_llm",
        billing_kind="llm_usage",
        app_kind="chat",
    )

    assert record_id is not None
    assert len(usage_record_repo.create_calls) == 1
    db.execute.assert_not_called()
