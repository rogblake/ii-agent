"""Unit tests for prepaid credit reservations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.billing.credits.service import CreditDeductionResult
from ii_agent.billing.reservations.service import CreditReservationService
from ii_agent.billing.reservations.types import BillingQuote

pytestmark = pytest.mark.unit


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


class FakeBalanceRepo:
    def __init__(self, *, credits: str = "10", bonus: str = "5", status: str = "ok"):
        self.credits = Decimal(credits)
        self.bonus = Decimal(bonus)
        self.status = status
        self.status_reason: str | None = None
        self.lock_balance_state_calls = 0

    async def lock_balance_state(self, db, user_id):
        self.lock_balance_state_calls += 1
        return self.credits, self.bonus, self.status

    async def lock_balance(self, db, user_id):
        return self.credits, self.bonus

    async def apply_delta_locked(
        self,
        db,
        user_id,
        *,
        delta_credits,
        delta_bonus_credits,
        billing_status=None,
        billing_status_reason=None,
    ):
        self.credits += Decimal(str(delta_credits))
        self.bonus += Decimal(str(delta_bonus_credits))
        if billing_status is not None:
            self.status = billing_status
            self.status_reason = billing_status_reason
        return self.credits, self.bonus, self.status

    async def set_billing_status(
        self,
        db,
        user_id,
        *,
        billing_status,
        billing_status_reason=None,
        expected_current_status=None,
    ):
        if expected_current_status is not None and self.status != expected_current_status:
            return False
        self.status = billing_status
        self.status_reason = billing_status_reason
        return True


class FakeLedgerRepo:
    def __init__(self):
        self.entries: list[dict] = []

    async def append(self, db, **kwargs):
        self.entries.append(kwargs)
        return SimpleNamespace(id=len(self.entries), **kwargs)


class FakeReservationRepo:
    def __init__(self):
        self.by_id: dict[str, SimpleNamespace] = {}
        self.by_idempotency: dict[str, SimpleNamespace] = {}
        self.counter = 0

    async def get_by_idempotency_key(self, db, idempotency_key):
        return self.by_idempotency.get(idempotency_key)

    async def create(self, db, **kwargs):
        self.counter += 1
        reservation = SimpleNamespace(
            id=f"reservation-{self.counter}",
            release_ledger_entry_id=None,
            shortfall_ledger_entry_id=None,
            usage_record_id=None,
            actual_credits=None,
            actual_bonus_credits=None,
            released_credits=None,
            released_bonus_credits=None,
            actual_usd=None,
            last_error=None,
            **kwargs,
        )
        self.by_id[reservation.id] = reservation
        if reservation.idempotency_key is not None:
            self.by_idempotency[reservation.idempotency_key] = reservation
        return reservation

    async def lock_by_id(self, db, reservation_id):
        return self.by_id.get(reservation_id)

    async def get_by_id(self, db, reservation_id):
        return self.by_id.get(reservation_id)

    async def list_stale_reserved(self, db, *, older_than, limit=100):
        reservations = [
            reservation
            for reservation in self.by_id.values()
            if reservation.status == "reserved"
            and reservation.expires_at is not None
            and reservation.expires_at < older_than
        ]
        return reservations[:limit]

    async def has_blocking_settlement_failures(self, db, *, user_id):
        return any(
            reservation.user_id == user_id and reservation.status == "settlement_failed"
            for reservation in self.by_id.values()
        )


class FakeCreditService:
    def __init__(self, deduct_result=None):
        self.deduct_result = deduct_result
        self.calls: list[dict] = []

    async def deduct(self, db, user_id, amount, **kwargs):
        self.calls.append({"user_id": user_id, "amount": amount, **kwargs})
        return self.deduct_result

    async def deduct_locked(self, db, user_id, amount, **kwargs):
        self.calls.append({"user_id": user_id, "amount": amount, **kwargs})
        return self.deduct_result


class FakeUsageService:
    def __init__(self):
        self.calls: list[dict] = []

    async def record_settled_usage(self, db, **kwargs):
        self.calls.append(kwargs)
        return 99


def _make_service(
    *,
    credits: str = "10",
    bonus: str = "5",
    credit_service: FakeCreditService | None = None,
):
    balance_repo = FakeBalanceRepo(credits=credits, bonus=bonus)
    ledger_repo = FakeLedgerRepo()
    reservation_repo = FakeReservationRepo()
    usage_service = FakeUsageService()
    service = CreditReservationService(
        balance_repo=balance_repo,
        ledger_repo=ledger_repo,
        reservation_repo=reservation_repo,
        credit_service=credit_service or FakeCreditService(),
        usage_service=usage_service,
    )
    return service, balance_repo, ledger_repo, reservation_repo, usage_service


@pytest.mark.asyncio
async def test_reserve_uses_bonus_then_regular_and_is_idempotent():
    service, balance_repo, ledger_repo, reservation_repo, _usage_service = _make_service(
        credits="4",
        bonus="3",
    )
    db = _make_db()
    quote = BillingQuote(
        strategy="bounded",
        reserve_usd=Decimal("0.075"),  # 5 credits
        max_usd=Decimal("0.075"),
    )

    hold = await service.reserve(
        db,
        user_id="user-1",
        subject_kind="session",
        subject_id="session-1",
        source_domain="chat_llm",
        source_id="call-1",
        billing_kind="llm_usage",
        quote=quote,
        idempotency_key="idem-1",
    )
    duplicate = await service.reserve(
        db,
        user_id="user-1",
        subject_kind="session",
        subject_id="session-1",
        source_domain="chat_llm",
        source_id="call-1",
        billing_kind="llm_usage",
        quote=quote,
        idempotency_key="idem-1",
    )

    assert hold is not None
    assert hold.reserved_bonus_credits == Decimal("3")
    assert hold.reserved_credits == Decimal("2")
    assert duplicate is not None
    assert duplicate.reservation_id == hold.reservation_id
    assert len(ledger_repo.entries) == 1
    assert balance_repo.credits == Decimal("2")
    assert balance_repo.bonus == Decimal("0")
    assert reservation_repo.by_id[hold.reservation_id].status == "reserved"


@pytest.mark.asyncio
async def test_settle_refunds_unused_reserved_split_and_records_usage():
    service, balance_repo, _ledger_repo, reservation_repo, usage_service = _make_service(
        credits="4",
        bonus="3",
    )
    db = _make_db()
    hold = await service.reserve(
        db,
        user_id="user-1",
        subject_kind="session",
        subject_id="session-1",
        source_domain="chat_llm",
        source_id="call-1",
        billing_kind="llm_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.075"),  # 5 credits
            max_usd=Decimal("0.075"),
        ),
        idempotency_key="idem-2",
    )

    result = await service.settle(
        db,
        reservation_id=hold.reservation_id,
        actual_credits=Decimal("4"),
        actual_usd=Decimal("0.06"),
        usage_payload={"app_kind": "chat", "provider": "anthropic"},
    )
    reservation = reservation_repo.by_id[hold.reservation_id]

    assert result.status == "settled"
    assert result.charged_bonus_credits == Decimal("3")
    assert result.charged_credits == Decimal("1")
    assert result.released_credits == Decimal("1")
    assert result.released_bonus_credits == Decimal("0")
    assert reservation.status == "settled"
    assert reservation.usage_record_id == 99
    assert balance_repo.credits == Decimal("3")
    assert balance_repo.bonus == Decimal("0")
    assert usage_service.calls[0]["amount"] == 4.0


@pytest.mark.asyncio
async def test_reserve_partially_holds_available_balance_within_controlled_shortfall_window():
    service, balance_repo, ledger_repo, reservation_repo, _usage_service = _make_service(
        credits="2",
        bonus="1",
    )
    db = _make_db()

    hold = await service.reserve(
        db,
        user_id="user-1",
        source_domain="chat_llm",
        source_id="call-partial",
        billing_kind="llm_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.075"),  # target hold: 5 credits
            max_usd=Decimal("0.075"),
        ),
        idempotency_key="idem-partial",
    )

    assert hold is not None
    assert hold.total_reserved == Decimal("3")
    assert hold.reserved_bonus_credits == Decimal("1")
    assert hold.reserved_credits == Decimal("2")
    assert balance_repo.credits == Decimal("0")
    assert balance_repo.bonus == Decimal("0")
    assert ledger_repo.entries[0]["entry_metadata"]["partial_reserve"] is True
    assert ledger_repo.entries[0]["entry_metadata"]["requested_reserve_credits"] == 5.0
    assert reservation_repo.by_id[hold.reservation_id].reserved_credits == Decimal("2")


@pytest.mark.asyncio
async def test_shortfall_failure_marks_reconciliation_required():
    credit_service = FakeCreditService(deduct_result=False)
    service, balance_repo, _ledger_repo, reservation_repo, usage_service = _make_service(
        credits="2",
        bonus="1",
        credit_service=credit_service,
    )
    db = _make_db()
    hold = await service.reserve(
        db,
        user_id="user-1",
        source_domain="agent_tool",
        source_id="tool-1",
        billing_kind="tool_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.075"),  # target hold: 5 credits, only 3 available
            max_usd=Decimal("0.075"),
        ),
        run_id="00000000-0000-0000-0000-000000000001",
        idempotency_key="idem-3",
    )

    result = await service.settle(
        db,
        reservation_id=hold.reservation_id,
        actual_credits=Decimal("5"),
        actual_usd=Decimal("0.075"),
        usage_payload={"app_kind": "agent", "tool_name": "generate_image"},
    )
    reservation = reservation_repo.by_id[hold.reservation_id]

    assert result.status == "settlement_failed"
    assert result.shortfall_detected is True
    assert reservation.status == "settlement_failed"
    assert reservation.last_error == "settlement_shortfall_unreconciled"
    assert balance_repo.status == "reconciliation_required"
    assert "Settlement shortfall" in (balance_repo.status_reason or "")
    # settlement_failed must NOT record usage — only fully settled reservations count
    assert len(usage_service.calls) == 0


@pytest.mark.asyncio
async def test_settlement_failed_reservation_can_retry_to_settled():
    service, _balance_repo, _ledger_repo, reservation_repo, usage_service = _make_service(
        credits="4",
        bonus="1",
    )
    db = _make_db()
    hold = await service.reserve(
        db,
        user_id="user-1",
        subject_kind="session",
        subject_id="session-1",
        source_domain="chat_llm",
        source_id="call-2",
        billing_kind="llm_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.045"),
            max_usd=Decimal("0.045"),
        ),
        idempotency_key="idem-retry",
    )

    await service.mark_settlement_failed(
        db,
        reservation_id=hold.reservation_id,
        error="transient_error",
    )
    result = await service.settle(
        db,
        reservation_id=hold.reservation_id,
        actual_credits=Decimal("2"),
        actual_usd=Decimal("0.03"),
        usage_payload={"app_kind": "chat", "request_kind": "chat_response"},
    )

    reservation = reservation_repo.by_id[hold.reservation_id]
    assert result.status == "settled"
    assert reservation.status == "settled"
    assert len(usage_service.calls) == 1
    assert _balance_repo.status == "ok"


@pytest.mark.asyncio
async def test_mark_settlement_failed_blocks_account_until_resolved():
    service, balance_repo, _ledger_repo, reservation_repo, _usage_service = _make_service(
        credits="4",
        bonus="1",
    )
    db = _make_db()
    hold = await service.reserve(
        db,
        user_id="user-1",
        subject_kind="session",
        subject_id="session-1",
        source_domain="chat_llm",
        source_id="call-block",
        billing_kind="llm_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.045"),
            max_usd=Decimal("0.045"),
        ),
        idempotency_key="idem-block",
    )

    await service.capture_settlement_input(
        db,
        reservation_id=hold.reservation_id,
        actual_credits=Decimal("2"),
        actual_usd=Decimal("0.03"),
        usage_payload={"app_kind": "chat", "request_kind": "chat_response"},
    )
    await service.mark_settlement_failed(
        db,
        reservation_id=hold.reservation_id,
        error="transient_error",
    )

    reservation = reservation_repo.by_id[hold.reservation_id]
    assert reservation.status == "settlement_failed"
    assert balance_repo.status == "reconciliation_required"
    assert "Settlement failed" in (balance_repo.status_reason or "")


@pytest.mark.asyncio
async def test_capture_settlement_input_persists_manual_retry_payload():
    service, _balance_repo, _ledger_repo, reservation_repo, _usage_service = _make_service()
    db = _make_db()
    hold = await service.reserve(
        db,
        user_id="user-1",
        subject_kind="session",
        subject_id="session-1",
        source_domain="chat_llm",
        source_id="call-capture",
        billing_kind="llm_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.03"),
            max_usd=Decimal("0.03"),
        ),
        idempotency_key="idem-capture",
    )

    await service.capture_settlement_input(
        db,
        reservation_id=hold.reservation_id,
        actual_credits=Decimal("1.25"),
        actual_usd=Decimal("0.01875"),
        usage_payload={"app_kind": "chat", "request_kind": "chat_response"},
    )

    reservation = reservation_repo.by_id[hold.reservation_id]
    capture = reservation.reservation_metadata["manual_settlement_capture"]
    assert capture["actual_credits"] == "1.25"
    assert capture["actual_usd"] == "0.01875"
    assert capture["usage_payload"]["request_kind"] == "chat_response"


@pytest.mark.asyncio
async def test_retry_settlement_from_capture_replays_stored_usage():
    service, _balance_repo, _ledger_repo, reservation_repo, usage_service = _make_service(
        credits="4",
        bonus="1",
    )
    db = _make_db()
    hold = await service.reserve(
        db,
        user_id="user-1",
        subject_kind="session",
        subject_id="session-1",
        source_domain="chat_llm",
        source_id="call-manual-retry",
        billing_kind="llm_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.045"),
            max_usd=Decimal("0.045"),
        ),
        idempotency_key="idem-manual-retry",
    )

    await service.capture_settlement_input(
        db,
        reservation_id=hold.reservation_id,
        actual_credits=Decimal("2"),
        actual_usd=Decimal("0.03"),
        usage_payload={"app_kind": "chat", "request_kind": "chat_response"},
    )
    await service.mark_settlement_failed(
        db,
        reservation_id=hold.reservation_id,
        error="transient_error",
    )

    result = await service.retry_settlement_from_capture(
        db,
        reservation_id=hold.reservation_id,
    )

    reservation = reservation_repo.by_id[hold.reservation_id]
    assert result.status == "settled"
    assert reservation.status == "settled"
    assert len(usage_service.calls) == 1


@pytest.mark.asyncio
async def test_expire_stale_releases_reservations():
    service, balance_repo, _ledger_repo, reservation_repo, _usage_service = _make_service(
        credits="4",
        bonus="1",
    )
    db = _make_db()
    hold = await service.reserve(
        db,
        user_id="user-1",
        source_domain="chat_tool",
        source_id="tool-1",
        billing_kind="tool_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.03"),  # 2 credits
            max_usd=Decimal("0.03"),
        ),
        idempotency_key="idem-4",
        expires_in=timedelta(seconds=-5),
    )

    expired = await service.expire_stale(
        db,
        older_than=datetime.now(timezone.utc),
    )
    reservation = reservation_repo.by_id[hold.reservation_id]

    assert expired == 1
    assert reservation.status == "expired"
    assert balance_repo.credits == Decimal("4")
    assert balance_repo.bonus == Decimal("1")


@pytest.mark.asyncio
async def test_expire_stale_replays_captured_settlement_input():
    service, balance_repo, _ledger_repo, reservation_repo, _usage_service = _make_service(
        credits="4",
        bonus="1",
    )
    db = _make_db()
    hold = await service.reserve(
        db,
        user_id="user-1",
        source_domain="chat_tool",
        source_id="tool-captured",
        billing_kind="tool_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.03"),
            max_usd=Decimal("0.03"),
        ),
        idempotency_key="idem-captured",
        expires_in=timedelta(seconds=-5),
    )

    await service.capture_settlement_input(
        db,
        reservation_id=hold.reservation_id,
        actual_credits=Decimal("2"),
        actual_usd=Decimal("0.03"),
        usage_payload={"app_kind": "chat", "provider": "anthropic"},
    )

    expired = await service.expire_stale(
        db,
        older_than=datetime.now(timezone.utc),
    )
    reservation = reservation_repo.by_id[hold.reservation_id]

    assert expired == 1
    assert reservation.status == "settled"
    assert balance_repo.credits == Decimal("3")
    assert balance_repo.bonus == Decimal("0")


# ---------------------------------------------------------------------------
# Test 5: zero credits or quote above the controlled window raises PaymentRequiredError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reserve_zero_balance_raises():
    from ii_agent.core.exceptions import PaymentRequiredError

    service, _balance_repo, _ledger_repo, _reservation_repo, _usage_service = _make_service(
        credits="0",
        bonus="0",
    )
    db = _make_db()

    with pytest.raises(PaymentRequiredError, match="Insufficient credits"):
        await service.reserve(
            db,
            user_id="user-1",
            source_domain="chat_llm",
            source_id="call-5",
            billing_kind="llm_usage",
            quote=BillingQuote(
                strategy="bounded",
                reserve_usd=Decimal("0.075"),  # 5 credits
                max_usd=Decimal("0.075"),
            ),
            idempotency_key="idem-5",
        )


@pytest.mark.asyncio
async def test_reserve_rejects_when_quote_exceeds_controlled_shortfall_window():
    from ii_agent.core.exceptions import PaymentRequiredError

    service, _balance_repo, _ledger_repo, _reservation_repo, _usage_service = _make_service(
        credits="2",
        bonus="1",
    )
    db = _make_db()

    with pytest.raises(PaymentRequiredError, match="Insufficient credits"):
        await service.reserve(
            db,
            user_id="user-1",
            source_domain="chat_llm",
            source_id="call-over-window",
            billing_kind="llm_usage",
            quote=BillingQuote(
                strategy="bounded",
                reserve_usd=Decimal("0.9"),  # 60 credits
                max_usd=Decimal("0.9"),
            ),
            idempotency_key="idem-over-window",
        )


# ---------------------------------------------------------------------------
# Test 6: billing_status != "ok" raises PaymentRequiredError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reserve_billing_reconciliation_required_raises():
    from ii_agent.core.exceptions import PaymentRequiredError

    balance_repo = FakeBalanceRepo(credits="10", bonus="5", status="reconciliation_required")
    ledger_repo = FakeLedgerRepo()
    reservation_repo = FakeReservationRepo()
    usage_service = FakeUsageService()
    service = CreditReservationService(
        balance_repo=balance_repo,
        ledger_repo=ledger_repo,
        reservation_repo=reservation_repo,
        credit_service=FakeCreditService(),
        usage_service=usage_service,
    )
    db = _make_db()

    with pytest.raises(PaymentRequiredError, match="reconciliation"):
        await service.reserve(
            db,
            user_id="user-1",
            source_domain="chat_llm",
            source_id="call-6",
            billing_kind="llm_usage",
            quote=BillingQuote(
                strategy="bounded",
                reserve_usd=Decimal("0.075"),  # 5 credits
                max_usd=Decimal("0.075"),
            ),
            idempotency_key="idem-6",
        )


# ---------------------------------------------------------------------------
# Test 7: settle with actual == reserved → no refund ledger entry, no release
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settle_exact_match_no_refund():
    service, balance_repo, ledger_repo, reservation_repo, usage_service = _make_service(
        credits="4",
        bonus="3",
    )
    db = _make_db()
    hold = await service.reserve(
        db,
        user_id="user-1",
        source_domain="chat_llm",
        source_id="call-7",
        billing_kind="llm_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.075"),  # 5 credits
            max_usd=Decimal("0.075"),
        ),
        idempotency_key="idem-7",
    )
    # One ledger entry written for the reservation hold
    reserve_entry_count = len(ledger_repo.entries)
    lock_calls_after_reserve = balance_repo.lock_balance_state_calls

    result = await service.settle(
        db,
        reservation_id=hold.reservation_id,
        actual_credits=Decimal("5"),  # exactly what was reserved
        actual_usd=Decimal("0.075"),
        usage_payload={"app_kind": "chat", "provider": "anthropic"},
    )

    # No additional ledger entries should have been written (no refund/release)
    assert len(ledger_repo.entries) == reserve_entry_count
    assert result.status == "settled"
    assert result.released_credits == Decimal("0")
    assert result.released_bonus_credits == Decimal("0")
    assert result.charged_bonus_credits == Decimal("3")
    assert result.charged_credits == Decimal("2")
    reservation = reservation_repo.by_id[hold.reservation_id]
    assert reservation.released_credits == Decimal("0")
    assert reservation.released_bonus_credits == Decimal("0")
    assert balance_repo.lock_balance_state_calls == lock_calls_after_reserve


# ---------------------------------------------------------------------------
# Test 8: settle with actual_credits=0 delegates to release
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settle_zero_actual_releases():
    service, balance_repo, _ledger_repo, reservation_repo, _usage_service = _make_service(
        credits="4",
        bonus="3",
    )
    db = _make_db()
    hold = await service.reserve(
        db,
        user_id="user-1",
        source_domain="chat_llm",
        source_id="call-8",
        billing_kind="llm_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.075"),  # 5 credits (3 bonus + 2 regular)
            max_usd=Decimal("0.075"),
        ),
        idempotency_key="idem-8",
    )
    credits_after_reserve = balance_repo.credits
    bonus_after_reserve = balance_repo.bonus

    result = await service.settle(
        db,
        reservation_id=hold.reservation_id,
        actual_credits=Decimal("0"),
        actual_usd=Decimal("0"),
        usage_payload={"app_kind": "chat"},
    )

    # All reserved credits should be returned to the balance
    assert result.status == "released"
    assert balance_repo.credits == credits_after_reserve + Decimal("2")
    assert balance_repo.bonus == bonus_after_reserve + Decimal("3")
    reservation = reservation_repo.by_id[hold.reservation_id]
    assert reservation.status in {"released", "expired"}


@pytest.mark.asyncio
async def test_settle_zero_actual_records_zero_cost_usage():
    service, _balance_repo, _ledger_repo, reservation_repo, usage_service = _make_service(
        credits="4",
        bonus="3",
    )
    db = _make_db()
    hold = await service.reserve(
        db,
        user_id="user-1",
        source_domain="chat_llm",
        source_id="call-8b",
        billing_kind="llm_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.075"),
            max_usd=Decimal("0.075"),
        ),
        idempotency_key="idem-8b",
    )

    result = await service.settle(
        db,
        reservation_id=hold.reservation_id,
        actual_credits=Decimal("0"),
        actual_usd=Decimal("0"),
        usage_payload={"app_kind": "chat", "provider": "anthropic", "input_tokens": 10},
    )

    assert result.status == "released"
    assert result.usage_record_id == 99
    assert len(usage_service.calls) == 1
    call = usage_service.calls[0]
    assert call["amount"] == 0.0
    assert call["cost_usd"] == 0.0
    assert call["usage_metadata"]["actual_requested_credits"] == 0.0
    assert call["usage_metadata"]["released_credits"] == 5.0
    assert call["usage_metadata"]["settlement_status"] == "released"
    assert reservation_repo.by_id[hold.reservation_id].usage_record_id == 99


# ---------------------------------------------------------------------------
# Test 9: settle on already-settled reservation returns existing result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settle_already_settled_returns_existing():
    service, balance_repo, _ledger_repo, _reservation_repo, usage_service = _make_service(
        credits="4",
        bonus="3",
    )
    db = _make_db()
    hold = await service.reserve(
        db,
        user_id="user-1",
        source_domain="chat_llm",
        source_id="call-9",
        billing_kind="llm_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.075"),  # 5 credits
            max_usd=Decimal("0.075"),
        ),
        idempotency_key="idem-9",
    )

    first = await service.settle(
        db,
        reservation_id=hold.reservation_id,
        actual_credits=Decimal("4"),
        actual_usd=Decimal("0.06"),
        usage_payload={"app_kind": "chat", "provider": "anthropic"},
    )
    lock_calls_after_first_settle = balance_repo.lock_balance_state_calls
    # Second settle call on the same already-settled reservation — must be a no-op
    second = await service.settle(
        db,
        reservation_id=hold.reservation_id,
        actual_credits=Decimal("4"),
        actual_usd=Decimal("0.06"),
        usage_payload={"app_kind": "chat", "provider": "anthropic"},
    )

    assert first.status == "settled"
    assert second.status == "settled"
    # usage_service must only have been called once, not twice
    assert len(usage_service.calls) == 1
    assert second.charged_credits == first.charged_credits
    assert second.charged_bonus_credits == first.charged_bonus_credits
    assert balance_repo.lock_balance_state_calls == lock_calls_after_first_settle


# ---------------------------------------------------------------------------
# Test 10: release on already-released reservation returns existing result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_release_already_released_returns_existing():
    service, balance_repo, _ledger_repo, reservation_repo, _usage_service = _make_service(
        credits="4",
        bonus="3",
    )
    db = _make_db()
    hold = await service.reserve(
        db,
        user_id="user-1",
        source_domain="chat_llm",
        source_id="call-10",
        billing_kind="llm_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.075"),  # 5 credits (3 bonus + 2 regular)
            max_usd=Decimal("0.075"),
        ),
        idempotency_key="idem-10",
    )
    credits_after_reserve = balance_repo.credits
    bonus_after_reserve = balance_repo.bonus

    first = await service.release(db, reservation_id=hold.reservation_id, reason="cancelled")
    lock_calls_after_first_release = balance_repo.lock_balance_state_calls
    # Second release call — must be idempotent, no double-refund
    second = await service.release(db, reservation_id=hold.reservation_id, reason="cancelled")

    assert first.status == "released"
    assert second.status == "released"
    # Balance must only have been restored once
    assert balance_repo.credits == credits_after_reserve + Decimal("2")
    assert balance_repo.bonus == bonus_after_reserve + Decimal("3")
    assert balance_repo.lock_balance_state_calls == lock_calls_after_first_release


@pytest.mark.asyncio
async def test_settle_already_released_returns_existing_release_result():
    service, balance_repo, _ledger_repo, reservation_repo, usage_service = _make_service(
        credits="4",
        bonus="3",
    )
    db = _make_db()
    hold = await service.reserve(
        db,
        user_id="user-1",
        source_domain="chat_llm",
        source_id="call-10b",
        billing_kind="llm_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.075"),  # 5 credits (3 bonus + 2 regular)
            max_usd=Decimal("0.075"),
        ),
        idempotency_key="idem-10b",
    )
    credits_after_reserve = balance_repo.credits
    bonus_after_reserve = balance_repo.bonus

    first = await service.release(db, reservation_id=hold.reservation_id, reason="cancelled")
    second = await service.settle(
        db,
        reservation_id=hold.reservation_id,
        actual_credits=Decimal("4"),
        actual_usd=Decimal("0.06"),
        usage_payload={"app_kind": "chat", "provider": "anthropic"},
    )

    assert first.status == "released"
    assert second.status == "released"
    assert balance_repo.credits == credits_after_reserve + Decimal("2")
    assert balance_repo.bonus == bonus_after_reserve + Decimal("3")
    assert reservation_repo.by_id[hold.reservation_id].status == "released"
    assert usage_service.calls == []


# ---------------------------------------------------------------------------
# Test 11: release on a settled reservation returns the settled result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_release_already_settled_returns_settled_result():
    service, _balance_repo, _ledger_repo, _reservation_repo, _usage_service = _make_service(
        credits="4",
        bonus="3",
    )
    db = _make_db()
    hold = await service.reserve(
        db,
        user_id="user-1",
        source_domain="chat_llm",
        source_id="call-11",
        billing_kind="llm_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.075"),  # 5 credits
            max_usd=Decimal("0.075"),
        ),
        idempotency_key="idem-11",
    )

    await service.settle(
        db,
        reservation_id=hold.reservation_id,
        actual_credits=Decimal("4"),
        actual_usd=Decimal("0.06"),
        usage_payload={"app_kind": "chat", "provider": "anthropic"},
    )

    # Releasing a settled reservation should surface the settled outcome
    result = await service.release(db, reservation_id=hold.reservation_id, reason="cancelled")

    assert result.status == "settled"
    assert result.charged_credits + result.charged_bonus_credits == Decimal("4")


# ---------------------------------------------------------------------------
# Test 12: shortfall success — overflow is charged, status remains "settled"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shortfall_success_charges_overflow():
    # Reserve 3 credits (0.045 USD), actual=5 → shortfall=2 credits.
    # The deduct call succeeds and returns a CreditDeductionResult.
    shortfall_deduction = CreditDeductionResult(
        ledger_entry_id=42,
        charged_credits=Decimal("-2"),
        charged_bonus_credits=Decimal("0"),
    )
    credit_service = FakeCreditService(deduct_result=shortfall_deduction)
    service, balance_repo, _ledger_repo, reservation_repo, usage_service = _make_service(
        credits="6",
        bonus="2",
        credit_service=credit_service,
    )
    db = _make_db()
    hold = await service.reserve(
        db,
        user_id="user-1",
        source_domain="agent_tool",
        source_id="tool-12",
        billing_kind="tool_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.045"),  # 3 credits (2 bonus + 1 regular)
            max_usd=Decimal("0.075"),
        ),
        idempotency_key="idem-12",
    )

    result = await service.settle(
        db,
        reservation_id=hold.reservation_id,
        actual_credits=Decimal("5"),  # 2 credits over the reservation
        actual_usd=Decimal("0.075"),
        usage_payload={"app_kind": "agent", "tool_name": "bash"},
    )
    reservation = reservation_repo.by_id[hold.reservation_id]

    assert result.status == "settled"
    assert result.shortfall_detected is True
    # Total charged = 3 reserved + 2 shortfall = 5
    assert result.charged_credits + result.charged_bonus_credits == Decimal("5")
    assert reservation.status == "settled"
    assert reservation.last_error is None
    # deduct must have been called once with the shortfall amount
    assert len(credit_service.calls) == 1
    assert credit_service.calls[0]["amount"] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Test 13: reserve with quote.reserve_usd=0 returns None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reserve_zero_amount_returns_none():
    service, balance_repo, ledger_repo, _reservation_repo, _usage_service = _make_service(
        credits="10",
        bonus="5",
    )
    db = _make_db()

    result = await service.reserve(
        db,
        user_id="user-1",
        source_domain="chat_llm",
        source_id="call-13",
        billing_kind="llm_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0"),
            max_usd=Decimal("0"),
        ),
        idempotency_key="idem-13",
    )

    assert result is None
    # No ledger entries should have been written
    assert len(ledger_repo.entries) == 0
    # Balance must remain unchanged
    assert balance_repo.credits == Decimal("10")
    assert balance_repo.bonus == Decimal("5")


# ---------------------------------------------------------------------------
# Test 14: settle records correct usage metadata fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settle_records_correct_usage_metadata():
    service, _balance_repo, _ledger_repo, reservation_repo, usage_service = _make_service(
        credits="10",
        bonus="5",
    )
    db = _make_db()
    hold = await service.reserve(
        db,
        user_id="user-1",
        subject_kind="session",
        subject_id="session-14",
        source_domain="chat_llm",
        source_id="call-14",
        billing_kind="llm_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.075"),  # 5 credits
            max_usd=Decimal("0.075"),
        ),
        run_id="run-14",
        model_id="claude-3-opus",
        idempotency_key="idem-14",
    )

    usage_payload = {
        "app_kind": "chat",
        "provider": "anthropic",
        "input_tokens": 100,
        "output_tokens": 200,
        "cache_read_tokens": 10,
        "cache_write_tokens": 5,
        "reasoning_tokens": 0,
        "latency_ms": 1500,
    }
    await service.settle(
        db,
        reservation_id=hold.reservation_id,
        actual_credits=Decimal("4"),
        actual_usd=Decimal("0.06"),
        usage_payload=usage_payload,
    )

    assert len(usage_service.calls) == 1
    call = usage_service.calls[0]

    # Top-level kwargs passed to record_settled_usage
    assert call["user_id"] == "user-1"
    assert call["subject_kind"] == "session"
    assert call["subject_id"] == "session-14"
    assert call["run_id"] == "run-14"
    assert call["model_id"] == "claude-3-opus"
    assert call["provider"] == "anthropic"
    assert call["input_tokens"] == 100
    assert call["output_tokens"] == 200
    assert call["cache_read_tokens"] == 10
    assert call["cache_write_tokens"] == 5
    assert call["latency_ms"] == 1500
    assert call["cost_usd"] == pytest.approx(0.06)
    assert call["app_kind"] == "chat"
    assert call["billing_kind"] == "llm_usage"
    assert call["amount"] == pytest.approx(4.0)

    # Embedded usage_metadata dict
    meta = call["usage_metadata"]
    assert meta["reservation_id"] == hold.reservation_id
    assert meta["actual_requested_credits"] == pytest.approx(4.0)
    assert meta["settlement_status"] == "settled"
    # 5 reserved - 4 actual = 1 credit refunded (from regular bucket)
    assert meta["released_credits"] == pytest.approx(1.0)
