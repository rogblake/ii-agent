"""End-to-end billing lifecycle tests.

Exercises the full shortfall → reconciliation → payment → recovery flow
using the same fake repos as the reservation service tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.billing.credits.balance_models import BillingStatus
from ii_agent.billing.credits.service import CreditService
from ii_agent.billing.exceptions import (
    BillingReconciliationRequiredError,
)
from ii_agent.billing.reservations.service import CreditReservationService
from ii_agent.billing.reservations.types import BillingQuote

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fakes (same pattern as test_credit_reservation_service.py)
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


class FakeBalanceRepo:
    def __init__(self, *, credits: str = "10", bonus: str = "5", status: str = "ok"):
        self.credits = Decimal(credits)
        self.bonus = Decimal(bonus)
        self.status = status
        self.status_reason: str | None = None
        self.lock_balance_state_calls = 0

    async def get_balance(self, db, user_id):
        return self.credits, self.bonus

    async def get_balance_with_updated_at(self, db, user_id):
        return self.credits, self.bonus, datetime.now(timezone.utc)

    async def get_billing_status(self, db, user_id):
        return self.status

    async def lock_balance(self, db, user_id):
        return self.credits, self.bonus

    async def lock_balance_state(self, db, user_id):
        self.lock_balance_state_calls += 1
        return self.credits, self.bonus, self.status

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

    async def get_or_create(self, db, user_id, **kwargs):
        return self.credits, self.bonus, False

    async def _apply_deduction(self, db, user_id, amount):
        amount = Decimal(str(amount))
        bonus_used = min(self.bonus, amount)
        regular_used = amount - bonus_used
        self.bonus -= bonus_used
        self.credits -= regular_used
        return self.credits, self.bonus

    async def set_credits(self, db, user_id, amount, bonus_amount=None):
        old_credits = self.credits
        old_bonus = self.bonus
        self.credits = Decimal(str(amount))
        if bonus_amount is not None:
            self.bonus = Decimal(str(bonus_amount))
        return old_credits, old_bonus, self.credits, self.bonus

    async def _set_credits_locked(self, db, user_id, amount, *, bonus_amount=None):
        self.credits = Decimal(str(amount))
        if bonus_amount is not None:
            self.bonus = Decimal(str(bonus_amount))
        return self.credits, self.bonus

    async def _apply_add_locked(self, db, user_id, amount, *, is_bonus=False):
        if is_bonus:
            self.bonus += Decimal(str(amount))
        else:
            self.credits += Decimal(str(amount))
        return self.credits, self.bonus

    async def add_credits(self, db, user_id, amount, is_bonus=False):
        old_credits = self.credits
        old_bonus = self.bonus
        if is_bonus:
            self.bonus += Decimal(str(amount))
        else:
            self.credits += Decimal(str(amount))
        return old_credits, old_bonus, self.credits, self.bonus


class FakeLedgerRepo:
    def __init__(self):
        self.entries: list[dict] = []
        self._seen_keys: set[str] = set()

    async def append(self, db, **kwargs):
        key = kwargs.get("idempotency_key")
        if key and key in self._seen_keys:
            return None  # duplicate
        if key:
            self._seen_keys.add(key)
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

    async def has_blocking_settlement_failures(self, db, *, user_id):
        return any(
            reservation.user_id == user_id and reservation.status == "settlement_failed"
            for reservation in self.by_id.values()
        )


class FakeUsageService:
    def __init__(self):
        self.calls: list[dict] = []

    async def record_settled_usage(self, db, **kwargs):
        self.calls.append(kwargs)
        return 99

    async def require_billing_ok(self, db, user_id):
        pass


# ---------------------------------------------------------------------------
# Lifecycle test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_shortfall_recovery_lifecycle():
    """
    1. Reserve credits
    2. Settle with shortfall → account blocked (reconciliation_required)
    3. New reserve attempt → rejected
    4. Simulate invoice.payment_succeeded → clear billing status + reset balance
    5. New reserve → succeeds
    """
    balance_repo = FakeBalanceRepo(credits="3", bonus="2", status="ok")
    ledger_repo = FakeLedgerRepo()
    reservation_repo = FakeReservationRepo()
    usage_service = FakeUsageService()

    # CreditService.deduct returns False to simulate shortfall failure
    credit_service = CreditService(balance_repo=balance_repo, ledger_repo=ledger_repo)

    reservation_service = CreditReservationService(
        balance_repo=balance_repo,
        ledger_repo=ledger_repo,
        reservation_repo=reservation_repo,
        credit_service=credit_service,
        usage_service=usage_service,
    )
    db = _make_db()

    # --- Step 1: Reserve 5 credits (3 regular + 2 bonus) ---
    hold = await reservation_service.reserve(
        db,
        user_id="user-1",
        source_domain="chat_llm",
        source_id="call-1",
        billing_kind="llm_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.075"),  # 5 credits
            max_usd=Decimal("0.075"),
        ),
        idempotency_key="lifecycle-1",
    )
    assert hold is not None
    # 5 credits reserved (2 bonus + 3 regular) from total of 5 → balance = 0
    assert balance_repo.credits == Decimal("0")
    assert balance_repo.bonus == Decimal("0")

    # --- Step 2: Settle with shortfall (actual=7, reserved=5, overflow=2) ---
    # The overflow deduction will fail because balance is only 1
    result = await reservation_service.settle(
        db,
        reservation_id=hold.reservation_id,
        actual_credits=Decimal("7"),
        actual_usd=Decimal("0.105"),
        usage_payload={"app_kind": "chat"},
    )
    assert result.status == "settlement_failed"
    assert result.shortfall_detected is True
    assert balance_repo.status == BillingStatus.RECONCILIATION_REQUIRED

    # --- Step 3: New reservation attempt → blocked ---
    with pytest.raises(BillingReconciliationRequiredError):
        await reservation_service.reserve(
            db,
            user_id="user-1",
            source_domain="chat_llm",
            source_id="call-2",
            billing_kind="llm_usage",
            quote=BillingQuote(
                strategy="bounded",
                reserve_usd=Decimal("0.015"),  # 1 credit
                max_usd=Decimal("0.015"),
            ),
            idempotency_key="lifecycle-2",
        )

    # --- Step 4: Simulate invoice.payment_succeeded ---
    # Webhook sets balance to plan credits and clears billing status.
    await credit_service.set_balance(
        db,
        "user-1",
        100.0,
        bonus_amount=10.0,
        entry_type="plan_change",
        source_domain="webhook",
        idempotency_key="webhook:invoice:evt_123",
    )
    await credit_service.clear_billing_status(db, "user-1")

    assert balance_repo.status == BillingStatus.OK
    assert balance_repo.credits == Decimal("100")
    assert balance_repo.bonus == Decimal("10")

    # --- Step 5: New reservation → succeeds ---
    hold2 = await reservation_service.reserve(
        db,
        user_id="user-1",
        source_domain="chat_llm",
        source_id="call-3",
        billing_kind="llm_usage",
        quote=BillingQuote(
            strategy="bounded",
            reserve_usd=Decimal("0.015"),  # 1 credit
            max_usd=Decimal("0.015"),
        ),
        idempotency_key="lifecycle-3",
    )
    assert hold2 is not None


@pytest.mark.asyncio
async def test_release_blocked_on_settlement_failed():
    """A SETTLEMENT_FAILED reservation cannot be released (work was delivered)."""
    balance_repo = FakeBalanceRepo(credits="10", bonus="5")
    ledger_repo = FakeLedgerRepo()
    reservation_repo = FakeReservationRepo()
    usage_service = FakeUsageService()
    credit_service = CreditService(balance_repo=balance_repo, ledger_repo=ledger_repo)

    service = CreditReservationService(
        balance_repo=balance_repo,
        ledger_repo=ledger_repo,
        reservation_repo=reservation_repo,
        credit_service=credit_service,
        usage_service=usage_service,
    )
    db = _make_db()

    hold = await service.reserve(
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
        idempotency_key="release-block-1",
    )

    # Mark as settlement_failed (simulating failed settle)
    await service.mark_settlement_failed(
        db,
        reservation_id=hold.reservation_id,
        error="transient_error",
    )

    credits_before = balance_repo.credits
    bonus_before = balance_repo.bonus

    # Attempt release — should be blocked (returns terminal result, no refund)
    result = await service.release(
        db,
        reservation_id=hold.reservation_id,
        reason="user_cancelled",
    )

    assert result.status == "settlement_failed"
    # Balance must NOT be restored
    assert balance_repo.credits == credits_before
    assert balance_repo.bonus == bonus_before
    assert balance_repo.status == BillingStatus.RECONCILIATION_REQUIRED


@pytest.mark.asyncio
async def test_webhook_credit_grant_is_idempotent():
    """Two calls with the same idempotency key should only set balance once."""
    balance_repo = FakeBalanceRepo(credits="50", bonus="0")
    ledger_repo = FakeLedgerRepo()
    credit_service = CreditService(balance_repo=balance_repo, ledger_repo=ledger_repo)
    db = _make_db()

    result1 = await credit_service.set_balance(
        db,
        "user-1",
        100.0,
        entry_type="plan_change",
        source_domain="webhook",
        idempotency_key="webhook:invoice:evt_456",
    )
    result2 = await credit_service.set_balance(
        db,
        "user-1",
        100.0,
        entry_type="plan_change",
        source_domain="webhook",
        idempotency_key="webhook:invoice:evt_456",
    )

    assert result1 is True
    assert result2 is None  # duplicate, skipped
    assert len(ledger_repo.entries) == 1  # only one ledger entry
