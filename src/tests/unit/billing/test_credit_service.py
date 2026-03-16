"""Unit tests for CreditService covering all service methods and the credit router."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from ii_agent.auth.dependencies import get_current_user
from ii_agent.billing.credits.dependencies import get_credit_service
from ii_agent.billing.credits.exceptions import CreditBalanceNotFoundError
from ii_agent.billing.credits.router import router as credits_router
from ii_agent.billing.credits.service import CreditDeductionResult, CreditService
from ii_agent.billing.usage.dependencies import get_usage_service
from ii_agent.core.dependencies import _db_session_dependency
from ii_agent.core.exceptions import IIAgentError
from ii_agent.core.middleware import ii_agent_error_handler

pytestmark = pytest.mark.unit

_USER_ID = str(uuid.uuid4())

# ---------------------------------------------------------------------------
# Fake repositories
# ---------------------------------------------------------------------------


class FakeCreditBalanceRepo:
    def __init__(self, credits: float = 10.0, bonus_credits: float = 5.0):
        self.balances = {
            _USER_ID: SimpleNamespace(credits=credits, bonus_credits=bonus_credits)
        }

    async def get_balance(self, db, user_id):
        bal = self.balances.get(user_id)
        if not bal:
            return None
        return (bal.credits, bal.bonus_credits)

    async def lock_balance(self, db, user_id):
        return await self.get_balance(db, user_id)

    async def get_balance_with_updated_at(self, db, user_id):
        bal = self.balances.get(user_id)
        if not bal:
            return None
        return (bal.credits, bal.bonus_credits, datetime.now(timezone.utc))

    async def check_sufficient(self, db, user_id, amount):
        bal = self.balances.get(user_id)
        if not bal:
            return False
        return (bal.credits + bal.bonus_credits) >= float(amount)

    async def get_or_create(self, db, user_id, **kwargs):
        bal = self.balances.get(user_id)
        if bal:
            return (bal.credits, bal.bonus_credits, False)
        credits = kwargs.get("credits", 0.0)
        bonus = kwargs.get("bonus_credits", 0.0)
        self.balances[user_id] = SimpleNamespace(credits=credits, bonus_credits=bonus)
        return (credits, bonus, True)

    async def deduct_credits(self, db, user_id, amount):
        bal = self.balances.get(user_id)
        if not bal:
            return None
        total = bal.credits + bal.bonus_credits
        if total < float(amount):
            return None
        old_credits = bal.credits
        old_bonus = bal.bonus_credits
        amount_f = float(amount)
        bonus_used = min(bal.bonus_credits, amount_f)
        regular_used = amount_f - bonus_used
        bal.bonus_credits -= bonus_used
        bal.credits -= regular_used
        return old_credits, old_bonus, bal.credits, bal.bonus_credits

    async def _apply_deduction(self, db, user_id, amount):
        bal = self.balances.get(user_id)
        if not bal:
            return None
        amount_f = float(amount)
        bonus_used = min(bal.bonus_credits, amount_f)
        regular_used = amount_f - bonus_used
        bal.bonus_credits -= bonus_used
        bal.credits -= regular_used
        return bal.credits, bal.bonus_credits

    async def add_credits(self, db, user_id, amount, is_bonus=False):
        bal = self.balances.get(user_id)
        if not bal:
            return None
        old_credits = bal.credits
        old_bonus = bal.bonus_credits
        amount_f = float(amount)
        if is_bonus:
            bal.bonus_credits += amount_f
        else:
            bal.credits += amount_f
        return old_credits, old_bonus, bal.credits, bal.bonus_credits

    async def set_credits(self, db, user_id, amount, bonus_amount=None):
        bal = self.balances.get(user_id)
        if not bal:
            return None
        old_credits = bal.credits
        old_bonus = bal.bonus_credits
        bal.credits = float(amount)
        if bonus_amount is not None:
            bal.bonus_credits = float(bonus_amount)
        return old_credits, old_bonus, bal.credits, bal.bonus_credits


class FakeCreditBalanceRepoEmpty:
    """Credit balance repo that returns no balances."""

    async def get_balance(self, db, user_id):
        return None

    async def lock_balance(self, db, user_id):
        return None

    async def get_balance_with_updated_at(self, db, user_id):
        return None

    async def check_sufficient(self, db, user_id, amount):
        return False

    async def get_or_create(self, db, user_id, **kwargs):
        return (kwargs.get("credits", 0.0), kwargs.get("bonus_credits", 0.0), True)

    async def deduct_credits(self, db, user_id, amount):
        return None

    async def _apply_deduction(self, db, user_id, amount):
        return None

    async def add_credits(self, db, user_id, amount, is_bonus=False):
        return None

    async def set_credits(self, db, user_id, amount, bonus_amount=None):
        return None


class FakeLedgerRepo:
    def __init__(self):
        self.entries = []

    async def append(self, db, **kwargs):
        self.entries.append(kwargs)
        return SimpleNamespace(id=len(self.entries), **kwargs)

    async def get_history(self, db, user_id, *, page=1, per_page=20):
        return self.entries, len(self.entries)


def _make_service(
    balance_repo=None, ledger_repo=None
) -> CreditService:
    return CreditService(
        balance_repo=balance_repo or FakeCreditBalanceRepo(),
        ledger_repo=ledger_repo or FakeLedgerRepo(),
    )


class _FakeNestedTransaction:
    """Async context manager that mimics ``db.begin_nested()``."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False  # propagate exceptions


def _make_fake_db():
    """Return a minimal fake async db session supporting begin_nested()."""
    db = MagicMock()
    db.begin_nested.return_value = _FakeNestedTransaction()
    return db


# ---------------------------------------------------------------------------
# Tests – get_balance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_balance_returns_credit_balance():
    """get_balance calls balance_repo.get_balance and returns a CreditBalance."""
    from ii_agent.billing.credits.schemas import CreditBalance

    balance_repo = FakeCreditBalanceRepo(credits=10.0, bonus_credits=5.0)
    svc = _make_service(balance_repo=balance_repo)

    result = await svc.get_balance(None, _USER_ID)

    assert result is not None
    assert result.credits == 10.0
    assert result.bonus_credits == 5.0
    assert result.user_id == _USER_ID


@pytest.mark.asyncio
async def test_get_balance_returns_none_when_user_not_found():
    """get_balance returns None when balance_repo has no entry for user."""
    balance_repo = FakeCreditBalanceRepoEmpty()
    svc = _make_service(balance_repo=balance_repo)

    result = await svc.get_balance(None, "nonexistent-user")

    assert result is None


# ---------------------------------------------------------------------------
# Tests – has_sufficient
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_has_sufficient_true_when_enough_credits():
    """Returns True when total balance >= amount."""
    svc = _make_service()

    assert await svc.has_sufficient(None, _USER_ID, 15.0) is True
    assert await svc.has_sufficient(None, _USER_ID, 14.9) is True


@pytest.mark.asyncio
async def test_has_sufficient_false_when_not_enough():
    """Returns False when total balance < amount."""
    balance_repo = FakeCreditBalanceRepo(credits=3.0, bonus_credits=2.0)
    svc = _make_service(balance_repo=balance_repo)

    assert await svc.has_sufficient(None, _USER_ID, 5.1) is False


@pytest.mark.asyncio
async def test_has_sufficient_false_when_user_not_found():
    """Returns False when user not found (balance is None)."""
    svc = _make_service(balance_repo=FakeCreditBalanceRepoEmpty())

    assert await svc.has_sufficient(None, "ghost", 1.0) is False


# ---------------------------------------------------------------------------
# Tests – deduct
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deduct_success_uses_bonus_first():
    """Deduction uses bonus credits before regular credits."""
    balance_repo = FakeCreditBalanceRepo(credits=10.0, bonus_credits=5.0)
    svc = _make_service(balance_repo=balance_repo)

    result = await svc.deduct(_make_fake_db(), _USER_ID, 3.0)

    assert isinstance(result, CreditDeductionResult)
    assert result.total_charged == Decimal("3.0")
    assert balance_repo.balances[_USER_ID].bonus_credits == 2.0
    assert balance_repo.balances[_USER_ID].credits == 10.0


@pytest.mark.asyncio
async def test_deduct_uses_regular_credits_when_bonus_exhausted():
    """When bonus runs out, regular credits are used."""
    balance_repo = FakeCreditBalanceRepo(credits=10.0, bonus_credits=2.0)
    svc = _make_service(balance_repo=balance_repo)

    result = await svc.deduct(_make_fake_db(), _USER_ID, 5.0)

    assert isinstance(result, CreditDeductionResult)
    assert result.total_charged == Decimal("5.0")
    assert balance_repo.balances[_USER_ID].bonus_credits == 0.0
    assert balance_repo.balances[_USER_ID].credits == 7.0


@pytest.mark.asyncio
async def test_deduct_returns_false_insufficient_balance():
    """Returns False when balance is insufficient."""
    balance_repo = FakeCreditBalanceRepo(credits=1.0, bonus_credits=0.5)
    svc = _make_service(balance_repo=balance_repo)

    result = await svc.deduct(_make_fake_db(), _USER_ID, 5.0)

    assert result is False


@pytest.mark.asyncio
async def test_deduct_returns_false_user_not_found():
    """Returns False when user doesn't exist."""
    svc = _make_service(balance_repo=FakeCreditBalanceRepoEmpty())

    result = await svc.deduct(_make_fake_db(), "nonexistent", 1.0)

    assert result is False


@pytest.mark.asyncio
async def test_deduct_raises_on_sqlalchemy_error():
    """Propagates SQLAlchemyError from balance repo."""
    balance_repo = MagicMock()
    balance_repo.lock_balance = AsyncMock(side_effect=SQLAlchemyError("DB failure"))
    svc = _make_service(balance_repo=balance_repo)

    with pytest.raises(SQLAlchemyError):
        await svc.deduct(_make_fake_db(), _USER_ID, 1.0)


# ---------------------------------------------------------------------------
# Tests – add
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_regular_credits():
    """add with is_bonus=False increases regular credits."""
    balance_repo = FakeCreditBalanceRepo(credits=10.0, bonus_credits=0.0)
    svc = _make_service(balance_repo=balance_repo)

    result = await svc.add(_make_fake_db(), _USER_ID, 5.0, is_bonus=False)

    assert result is True
    assert balance_repo.balances[_USER_ID].credits == 15.0


@pytest.mark.asyncio
async def test_add_bonus_credits():
    """add with is_bonus=True increases bonus credits."""
    balance_repo = FakeCreditBalanceRepo(credits=0.0, bonus_credits=2.0)
    svc = _make_service(balance_repo=balance_repo)

    result = await svc.add(_make_fake_db(), _USER_ID, 3.0, is_bonus=True)

    assert result is True
    assert balance_repo.balances[_USER_ID].bonus_credits == 5.0


@pytest.mark.asyncio
async def test_add_returns_false_user_not_found():
    """Returns False when user doesn't exist."""
    svc = _make_service(balance_repo=FakeCreditBalanceRepoEmpty())

    result = await svc.add(_make_fake_db(), "ghost", 10.0)

    assert result is False


@pytest.mark.asyncio
async def test_add_raises_on_sqlalchemy_error():
    """Propagates SQLAlchemyError."""
    balance_repo = MagicMock()
    balance_repo.lock_balance = AsyncMock(side_effect=SQLAlchemyError("DB error"))
    svc = _make_service(balance_repo=balance_repo)

    with pytest.raises(SQLAlchemyError):
        await svc.add(_make_fake_db(), _USER_ID, 1.0)


# ---------------------------------------------------------------------------
# Tests – set_balance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_balance_sets_both_amounts():
    """set_balance sets regular and bonus credits."""
    balance_repo = FakeCreditBalanceRepo(credits=10.0, bonus_credits=5.0)
    db = _make_fake_db()
    svc = _make_service(balance_repo=balance_repo)

    result = await svc.set_balance(db, _USER_ID, 50.0, bonus_amount=10.0)

    assert result is True
    assert balance_repo.balances[_USER_ID].credits == 50.0
    assert balance_repo.balances[_USER_ID].bonus_credits == 10.0


@pytest.mark.asyncio
async def test_set_balance_without_bonus_amount():
    """set_balance without bonus_amount keeps original bonus credits."""
    balance_repo = FakeCreditBalanceRepo(credits=5.0, bonus_credits=3.0)
    db = _make_fake_db()
    svc = _make_service(balance_repo=balance_repo)

    result = await svc.set_balance(db, _USER_ID, 100.0)

    assert result is True
    assert balance_repo.balances[_USER_ID].credits == 100.0
    # bonus_credits unchanged by None bonus_amount
    assert balance_repo.balances[_USER_ID].bonus_credits == 3.0


@pytest.mark.asyncio
async def test_set_balance_returns_false_user_not_found():
    """Returns False when user doesn't exist."""
    db = _make_fake_db()
    svc = _make_service(balance_repo=FakeCreditBalanceRepoEmpty())

    result = await svc.set_balance(db, "ghost", 10.0)

    assert result is False


@pytest.mark.asyncio
async def test_set_balance_raises_on_sqlalchemy_error():
    """Propagates SQLAlchemyError."""
    db = _make_fake_db()
    balance_repo = MagicMock()
    balance_repo.get_or_create = AsyncMock(return_value=(0.0, 0.0, True))
    balance_repo.lock_balance = AsyncMock(side_effect=SQLAlchemyError("DB error"))
    svc = _make_service(balance_repo=balance_repo)

    with pytest.raises(SQLAlchemyError):
        await svc.set_balance(db, _USER_ID, 10.0)


# ---------------------------------------------------------------------------
# Tests – Credits Router
# ---------------------------------------------------------------------------


def _make_user(user_id: str = _USER_ID) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, email="test@example.com", is_active=True)


def _build_credits_app(
    credit_service: MagicMock, usage_service: MagicMock | None = None
) -> FastAPI:
    app = FastAPI()
    app.include_router(credits_router)
    app.add_exception_handler(IIAgentError, ii_agent_error_handler)

    app.dependency_overrides[get_current_user] = lambda: _make_user()
    app.dependency_overrides[_db_session_dependency] = lambda: AsyncMock()
    app.dependency_overrides[get_credit_service] = lambda: credit_service
    if usage_service is not None:
        app.dependency_overrides[get_usage_service] = lambda: usage_service

    return app


def _make_credit_service_mock(*, balance=None) -> MagicMock:
    svc = MagicMock()
    svc.get_balance = AsyncMock(return_value=balance)
    return svc


def _make_usage_service_mock(
    *, history_result=None, history_total: int = 0
) -> MagicMock:
    svc = MagicMock()
    svc.get_history = AsyncMock(return_value=(history_result or [], history_total))
    return svc


def test_get_credit_balance_success():
    """GET /credits/balance returns credit balance for current user."""
    from ii_agent.billing.credits.schemas import CreditBalance

    balance = CreditBalance(
        user_id=_USER_ID,
        credits=50.0,
        bonus_credits=10.0,
        updated_at=datetime.now(timezone.utc),
    )
    svc = _make_credit_service_mock(balance=balance)

    app = _build_credits_app(svc)
    client = TestClient(app)
    resp = client.get("/credits/balance")

    assert resp.status_code == 200
    data = resp.json()
    assert data["credits"] == 50.0
    assert data["bonus_credits"] == 10.0
    assert data["user_id"] == _USER_ID


def test_get_credit_balance_not_found_returns_404():
    """GET /credits/balance returns 404 when no balance found."""
    svc = _make_credit_service_mock(balance=None)

    app = _build_credits_app(svc)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/credits/balance")

    assert resp.status_code == 404


def test_get_credit_usage_success():
    """GET /credits/usage returns paginated credit history."""
    from ii_agent.billing.credits.schemas import CreditBalance

    balance = CreditBalance(
        user_id=_USER_ID,
        credits=10.0,
        bonus_credits=0.0,
        updated_at=datetime.now(timezone.utc),
    )
    history = [
        {
            "session_id": str(uuid.uuid4()),
            "session_title": "My Session",
            "credits": 2.5,
            "updated_at": datetime.now(timezone.utc),
        }
    ]
    credit_svc = _make_credit_service_mock(balance=balance)
    usage_svc = _make_usage_service_mock(history_result=history, history_total=1)

    app = _build_credits_app(credit_svc, usage_svc)
    client = TestClient(app)
    resp = client.get("/credits/usage")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["credits"] == 2.5


def test_get_credit_usage_balance_not_found_returns_404():
    """GET /credits/usage returns 404 when no balance."""
    svc = _make_credit_service_mock(balance=None)

    app = _build_credits_app(svc)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/credits/usage")

    assert resp.status_code == 404


def test_get_credit_usage_pagination():
    """GET /credits/usage respects pagination params."""
    from ii_agent.billing.credits.schemas import CreditBalance

    balance = CreditBalance(
        user_id=_USER_ID,
        credits=5.0,
        bonus_credits=0.0,
        updated_at=datetime.now(timezone.utc),
    )
    credit_svc = _make_credit_service_mock(balance=balance)
    usage_svc = _make_usage_service_mock(history_result=[], history_total=0)

    app = _build_credits_app(credit_svc, usage_svc)
    client = TestClient(app)
    resp = client.get("/credits/usage?page=2&per_page=5")

    assert resp.status_code == 200
    call_kwargs = usage_svc.get_history.call_args.kwargs
    assert call_kwargs.get("page") == 2
    assert call_kwargs.get("per_page") == 5


def test_get_credit_usage_empty_history():
    """GET /credits/usage with no history returns empty list."""
    from ii_agent.billing.credits.schemas import CreditBalance

    balance = CreditBalance(
        user_id=_USER_ID,
        credits=5.0,
        bonus_credits=0.0,
        updated_at=datetime.now(timezone.utc),
    )
    credit_svc = _make_credit_service_mock(balance=balance)
    usage_svc = _make_usage_service_mock(history_result=[], history_total=0)

    app = _build_credits_app(credit_svc, usage_svc)
    client = TestClient(app)
    resp = client.get("/credits/usage")

    assert resp.status_code == 200
    data = resp.json()
    assert data["sessions"] == []
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# Tests – Credits Router: /credits/ledger
# ---------------------------------------------------------------------------


def _make_ledger_entry_ns(
    entry_id: int = 1,
    entry_type: str = "deduction",
    delta_credits: float = -2.0,
    delta_bonus_credits: float = 0.0,
):
    """Create a SimpleNamespace mimicking a CreditLedgerEntry for model_validate."""
    return SimpleNamespace(
        id=entry_id,
        entry_type=entry_type,
        source_domain="llm_usage",
        source_id="sess-1",
        delta_credits=delta_credits,
        delta_bonus_credits=delta_bonus_credits,
        idempotency_key=None,
        entry_metadata=None,
        created_at=datetime.now(timezone.utc),
    )


def test_get_credit_ledger_success():
    """GET /credits/ledger returns paginated ledger entries."""
    entries = [_make_ledger_entry_ns(1, "deduction", -2.0), _make_ledger_entry_ns(2, "grant", 10.0)]
    svc = _make_credit_service_mock()
    svc.get_ledger_history = AsyncMock(return_value=(entries, 2))

    app = _build_credits_app(svc)
    client = TestClient(app)
    resp = client.get("/credits/ledger")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["entries"]) == 2
    assert data["entries"][0]["entry_type"] == "deduction"
    assert data["entries"][1]["entry_type"] == "grant"


def test_get_credit_ledger_empty():
    """GET /credits/ledger with no entries returns empty list."""
    svc = _make_credit_service_mock()
    svc.get_ledger_history = AsyncMock(return_value=([], 0))

    app = _build_credits_app(svc)
    client = TestClient(app)
    resp = client.get("/credits/ledger")

    assert resp.status_code == 200
    data = resp.json()
    assert data["entries"] == []
    assert data["total"] == 0


def test_get_credit_ledger_pagination():
    """GET /credits/ledger respects pagination params."""
    svc = _make_credit_service_mock()
    svc.get_ledger_history = AsyncMock(return_value=([], 0))

    app = _build_credits_app(svc)
    client = TestClient(app)
    resp = client.get("/credits/ledger?page=3&per_page=10")

    assert resp.status_code == 200
    call_kwargs = svc.get_ledger_history.call_args.kwargs
    assert call_kwargs.get("page") == 3
    assert call_kwargs.get("per_page") == 10
