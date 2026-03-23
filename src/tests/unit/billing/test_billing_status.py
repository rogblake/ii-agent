"""Tests for billing status lifecycle: require_billing_ok, clear_billing_status."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.billing.credits.balance_models import BillingStatus
from ii_agent.billing.credits.service import CreditService
from ii_agent.billing.exceptions import BillingReconciliationRequiredError

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeNestedTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


class FakeBalanceRepo:
    def __init__(self, *, billing_status: str = "ok"):
        self._billing_status = billing_status
        self._billing_status_reason: str | None = (
            "prior shortfall" if billing_status != "ok" else None
        )
        self.lock_balance_state_calls = 0

    async def get_billing_status(self, db, user_id):
        return self._billing_status

    async def lock_balance_state(self, db, user_id):
        self.lock_balance_state_calls += 1
        return Decimal("10"), Decimal("5"), self._billing_status

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
        if billing_status is not None:
            self._billing_status = billing_status
            self._billing_status_reason = billing_status_reason
        return Decimal("10"), Decimal("5"), self._billing_status

    async def set_billing_status(
        self,
        db,
        user_id,
        *,
        billing_status,
        billing_status_reason=None,
        expected_current_status=None,
    ):
        if expected_current_status is not None and self._billing_status != expected_current_status:
            return False
        self._billing_status = billing_status
        self._billing_status_reason = billing_status_reason
        return True


def _make_db():
    db = MagicMock()
    db.begin_nested.return_value = _FakeNestedTransaction()
    db.flush = AsyncMock()
    return db


def _make_service(*, billing_status: str = "ok") -> tuple[CreditService, FakeBalanceRepo]:
    balance_repo = FakeBalanceRepo(billing_status=billing_status)
    service = CreditService(balance_repo=balance_repo)
    return service, balance_repo


# ---------------------------------------------------------------------------
# require_billing_ok
# ---------------------------------------------------------------------------


class TestRequireBillingOk:
    @pytest.mark.asyncio
    async def test_passes_when_status_is_ok(self):
        service, _ = _make_service(billing_status="ok")
        # Should not raise
        await service.require_billing_ok(_make_db(), "user-1")

    @pytest.mark.asyncio
    async def test_raises_when_reconciliation_required(self):
        service, _ = _make_service(billing_status="reconciliation_required")
        with pytest.raises(BillingReconciliationRequiredError):
            await service.require_billing_ok(_make_db(), "user-1")

    @pytest.mark.asyncio
    async def test_passes_when_no_balance_row(self):
        """Users without a credit_balances row should not be blocked."""
        balance_repo = FakeBalanceRepo()
        balance_repo.get_billing_status = AsyncMock(return_value=None)
        service = CreditService(balance_repo=balance_repo)
        # Should not raise
        await service.require_billing_ok(_make_db(), "user-1")


# ---------------------------------------------------------------------------
# clear_billing_status
# ---------------------------------------------------------------------------


class TestClearBillingStatus:
    @pytest.mark.asyncio
    async def test_clears_reconciliation_required_to_ok(self):
        service, balance_repo = _make_service(billing_status="reconciliation_required")
        db = _make_db()

        result = await service.clear_billing_status(db, "user-1")

        assert result is True
        assert balance_repo._billing_status == BillingStatus.OK
        assert balance_repo._billing_status_reason is None
        assert balance_repo.lock_balance_state_calls == 0

    @pytest.mark.asyncio
    async def test_returns_false_when_already_ok(self):
        service, balance_repo = _make_service(billing_status="ok")
        db = _make_db()

        result = await service.clear_billing_status(db, "user-1")

        assert result is False
        assert balance_repo._billing_status == "ok"

    @pytest.mark.asyncio
    async def test_returns_false_when_user_not_found(self):
        service, balance_repo = _make_service()
        balance_repo.set_billing_status = AsyncMock(return_value=False)
        db = _make_db()

        result = await service.clear_billing_status(db, "missing-user")

        assert result is False

    @pytest.mark.asyncio
    async def test_is_idempotent(self):
        """Calling clear twice should succeed both times without side effects."""
        service, balance_repo = _make_service(billing_status="reconciliation_required")
        db = _make_db()

        first = await service.clear_billing_status(db, "user-1")
        second = await service.clear_billing_status(db, "user-1")

        assert first is True
        assert second is False  # already ok
        assert balance_repo._billing_status == BillingStatus.OK
