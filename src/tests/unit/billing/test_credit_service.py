"""Unit tests for CreditService covering all service methods and the credit router."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
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
from ii_agent.billing.credits.service import CreditService
from ii_agent.core.dependencies import _db_session_dependency
from ii_agent.core.exceptions import IIAgentError
from ii_agent.core.middleware import ii_agent_error_handler

pytestmark = pytest.mark.unit

_USER_ID = str(uuid.uuid4())

# ---------------------------------------------------------------------------
# Fake repositories (same pattern as existing test_credit_service.py)
# ---------------------------------------------------------------------------


class FakeUserRepo:
    def __init__(self, credits: float = 10.0, bonus_credits: float = 5.0):
        self.users = {
            _USER_ID: SimpleNamespace(
                id=_USER_ID,
                credits=credits,
                bonus_credits=bonus_credits,
            )
        }

    async def deduct_credits(self, db, user_id, amount):
        user = self.users.get(user_id)
        if not user:
            return None
        total = user.credits + user.bonus_credits
        if total < amount:
            return None
        bonus_used = min(user.bonus_credits, amount)
        regular_used = amount - bonus_used
        user.bonus_credits -= bonus_used
        user.credits -= regular_used
        return user.credits, user.bonus_credits

    async def add_credits(self, db, user_id, amount, is_bonus=False):
        user = self.users.get(user_id)
        if not user:
            return None
        if is_bonus:
            user.bonus_credits += amount
        else:
            user.credits += amount
        return user.credits, user.bonus_credits

    async def set_credits(self, db, user_id, amount, bonus_amount=None):
        user = self.users.get(user_id)
        if not user:
            return None
        user.credits = amount
        if bonus_amount is not None:
            user.bonus_credits = bonus_amount
        return user.credits, user.bonus_credits

    async def get_by_id(self, db, user_id):
        return self.users.get(user_id)


class FakeUserRepoEmpty:
    """User repo that returns no users."""

    async def deduct_credits(self, db, user_id, amount):
        return None

    async def add_credits(self, db, user_id, amount, is_bonus=False):
        return None

    async def set_credits(self, db, user_id, amount, bonus_amount=None):
        return None

    async def get_by_id(self, db, user_id):
        return None


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


def _make_service(
    user_repo=None, metrics_repo=None
) -> CreditService:
    return CreditService(
        user_repo=user_repo or FakeUserRepo(),
        metrics_repo=metrics_repo or FakeMetricsRepo(),
    )


# ---------------------------------------------------------------------------
# Tests – get_balance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_balance_returns_credit_balance(monkeypatch):
    """get_balance queries the DB and returns a CreditBalance."""
    from ii_agent.billing.credits.schemas import CreditBalance

    async def _fake_execute(stmt):
        row = SimpleNamespace(
            credits=10.0,
            bonus_credits=5.0,
            updated_at=datetime.now(timezone.utc),
        )
        return SimpleNamespace(first=lambda: row)

    db = SimpleNamespace(execute=_fake_execute)
    svc = _make_service()

    result = await svc.get_balance(db, _USER_ID)

    assert result is not None
    assert result.credits == 10.0
    assert result.bonus_credits == 5.0
    assert result.user_id == _USER_ID


@pytest.mark.asyncio
async def test_get_balance_returns_none_when_user_not_found(monkeypatch):
    """get_balance returns None when DB has no row for user."""
    async def _fake_execute(stmt):
        return SimpleNamespace(first=lambda: None)

    db = SimpleNamespace(execute=_fake_execute)
    svc = _make_service()

    result = await svc.get_balance(db, "nonexistent-user")

    assert result is None


# ---------------------------------------------------------------------------
# Tests – has_sufficient
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_has_sufficient_true_when_enough_credits():
    """Returns True when total balance >= amount."""
    svc = _make_service()

    # Monkeypatch get_balance to return known balance
    async def _fake_balance(db, user_id):
        return SimpleNamespace(credits=10.0, bonus_credits=5.0)

    svc.get_balance = _fake_balance

    assert await svc.has_sufficient(None, _USER_ID, 15.0) is True
    assert await svc.has_sufficient(None, _USER_ID, 14.9) is True


@pytest.mark.asyncio
async def test_has_sufficient_false_when_not_enough():
    """Returns False when total balance < amount."""
    svc = _make_service()

    async def _fake_balance(db, user_id):
        return SimpleNamespace(credits=3.0, bonus_credits=2.0)

    svc.get_balance = _fake_balance

    assert await svc.has_sufficient(None, _USER_ID, 5.1) is False


@pytest.mark.asyncio
async def test_has_sufficient_false_when_user_not_found():
    """Returns False when user not found (balance is None)."""
    svc = _make_service()

    async def _fake_balance(db, user_id):
        return None

    svc.get_balance = _fake_balance

    assert await svc.has_sufficient(None, "ghost", 1.0) is False


# ---------------------------------------------------------------------------
# Tests – deduct
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deduct_success_uses_bonus_first():
    """Deduction uses bonus credits before regular credits."""
    user_repo = FakeUserRepo(credits=10.0, bonus_credits=5.0)
    svc = _make_service(user_repo=user_repo)

    result = await svc.deduct(None, _USER_ID, 3.0)

    assert result is True
    assert user_repo.users[_USER_ID].bonus_credits == 2.0
    assert user_repo.users[_USER_ID].credits == 10.0


@pytest.mark.asyncio
async def test_deduct_uses_regular_credits_when_bonus_exhausted():
    """When bonus runs out, regular credits are used."""
    user_repo = FakeUserRepo(credits=10.0, bonus_credits=2.0)
    svc = _make_service(user_repo=user_repo)

    result = await svc.deduct(None, _USER_ID, 5.0)

    assert result is True
    assert user_repo.users[_USER_ID].bonus_credits == 0.0
    assert user_repo.users[_USER_ID].credits == 7.0


@pytest.mark.asyncio
async def test_deduct_returns_false_insufficient_balance():
    """Returns False when balance is insufficient."""
    user_repo = FakeUserRepo(credits=1.0, bonus_credits=0.5)
    svc = _make_service(user_repo=user_repo)

    result = await svc.deduct(None, _USER_ID, 5.0)

    assert result is False


@pytest.mark.asyncio
async def test_deduct_returns_false_user_not_found():
    """Returns False when user doesn't exist."""
    svc = _make_service(user_repo=FakeUserRepoEmpty())

    result = await svc.deduct(None, "nonexistent", 1.0)

    assert result is False


@pytest.mark.asyncio
async def test_deduct_raises_on_sqlalchemy_error():
    """Propagates SQLAlchemyError from user repo."""
    user_repo = MagicMock()
    user_repo.deduct_credits = AsyncMock(side_effect=SQLAlchemyError("DB failure"))
    svc = _make_service(user_repo=user_repo)

    with pytest.raises(SQLAlchemyError):
        await svc.deduct(None, _USER_ID, 1.0)


# ---------------------------------------------------------------------------
# Tests – add
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_regular_credits():
    """add with is_bonus=False increases regular credits."""
    user_repo = FakeUserRepo(credits=10.0, bonus_credits=0.0)
    svc = _make_service(user_repo=user_repo)

    result = await svc.add(None, _USER_ID, 5.0, is_bonus=False)

    assert result is True
    assert user_repo.users[_USER_ID].credits == 15.0


@pytest.mark.asyncio
async def test_add_bonus_credits():
    """add with is_bonus=True increases bonus credits."""
    user_repo = FakeUserRepo(credits=0.0, bonus_credits=2.0)
    svc = _make_service(user_repo=user_repo)

    result = await svc.add(None, _USER_ID, 3.0, is_bonus=True)

    assert result is True
    assert user_repo.users[_USER_ID].bonus_credits == 5.0


@pytest.mark.asyncio
async def test_add_returns_false_user_not_found():
    """Returns False when user doesn't exist."""
    svc = _make_service(user_repo=FakeUserRepoEmpty())

    result = await svc.add(None, "ghost", 10.0)

    assert result is False


@pytest.mark.asyncio
async def test_add_raises_on_sqlalchemy_error():
    """Propagates SQLAlchemyError."""
    user_repo = MagicMock()
    user_repo.add_credits = AsyncMock(side_effect=SQLAlchemyError("DB error"))
    svc = _make_service(user_repo=user_repo)

    with pytest.raises(SQLAlchemyError):
        await svc.add(None, _USER_ID, 1.0)


# ---------------------------------------------------------------------------
# Tests – set_balance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_balance_sets_both_amounts():
    """set_balance sets regular and bonus credits."""
    user_repo = FakeUserRepo()
    svc = _make_service(user_repo=user_repo)

    result = await svc.set_balance(None, _USER_ID, 50.0, bonus_amount=10.0)

    assert result is True
    assert user_repo.users[_USER_ID].credits == 50.0
    assert user_repo.users[_USER_ID].bonus_credits == 10.0


@pytest.mark.asyncio
async def test_set_balance_without_bonus_amount():
    """set_balance without bonus_amount keeps original bonus credits."""
    user_repo = FakeUserRepo(credits=5.0, bonus_credits=3.0)
    svc = _make_service(user_repo=user_repo)

    result = await svc.set_balance(None, _USER_ID, 100.0)

    assert result is True
    assert user_repo.users[_USER_ID].credits == 100.0
    # bonus_credits unchanged by None bonus_amount
    assert user_repo.users[_USER_ID].bonus_credits == 3.0


@pytest.mark.asyncio
async def test_set_balance_returns_false_user_not_found():
    """Returns False when user doesn't exist."""
    svc = _make_service(user_repo=FakeUserRepoEmpty())

    result = await svc.set_balance(None, "ghost", 10.0)

    assert result is False


@pytest.mark.asyncio
async def test_set_balance_raises_on_sqlalchemy_error():
    """Propagates SQLAlchemyError."""
    user_repo = MagicMock()
    user_repo.set_credits = AsyncMock(side_effect=SQLAlchemyError("DB error"))
    svc = _make_service(user_repo=user_repo)

    with pytest.raises(SQLAlchemyError):
        await svc.set_balance(None, _USER_ID, 10.0)


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
    """Successful deduction calls accumulate_session_usage."""
    metrics_repo = FakeMetricsRepo()
    svc = _make_service(metrics_repo=metrics_repo)

    result = await svc.deduct_and_track_session_usage(
        None, user_id=_USER_ID, session_id="sess-1", amount=2.0
    )

    assert result is True
    # Session usage is accumulated as negative (consumption)
    record = metrics_repo.records.get("sess-1")
    assert record is not None
    assert record.credits == -2.0


@pytest.mark.asyncio
async def test_deduct_and_track_returns_false_when_insufficient():
    """Returns False when deduction fails (insufficient balance)."""
    user_repo = FakeUserRepo(credits=0.5, bonus_credits=0.0)
    svc = _make_service(user_repo=user_repo)

    result = await svc.deduct_and_track_session_usage(
        None, user_id=_USER_ID, session_id="sess-1", amount=5.0
    )

    assert result is False


# ---------------------------------------------------------------------------
# Tests – accumulate_session_usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accumulate_session_usage_creates_new_record():
    """Creates new metrics record when none exists."""
    metrics_repo = FakeMetricsRepo()
    svc = _make_service(metrics_repo=metrics_repo)

    await svc.accumulate_session_usage(None, "new-session", -1.5)

    record = metrics_repo.records.get("new-session")
    assert record is not None
    assert record.credits == -1.5


@pytest.mark.asyncio
async def test_accumulate_session_usage_updates_existing_record():
    """Updates existing record by adding to it."""
    metrics_repo = FakeMetricsRepo()
    await metrics_repo.create(None, "existing-session", -1.0)
    svc = _make_service(metrics_repo=metrics_repo)

    await svc.accumulate_session_usage(None, "existing-session", -2.5)

    record = metrics_repo.records["existing-session"]
    assert record.credits == pytest.approx(-3.5)


@pytest.mark.asyncio
async def test_accumulate_session_usage_raises_on_error():
    """Propagates exceptions from metrics repo."""
    metrics_repo = MagicMock()
    metrics_repo.get_by_session_id = AsyncMock(side_effect=Exception("Repo error"))
    svc = _make_service(metrics_repo=metrics_repo)

    with pytest.raises(Exception, match="Repo error"):
        await svc.accumulate_session_usage(None, "sess", -1.0)


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
# Tests – Credits Router
# ---------------------------------------------------------------------------


def _make_user(user_id: str = _USER_ID) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, email="test@example.com", is_active=True)


def _build_credits_app(credit_service: MagicMock) -> FastAPI:
    app = FastAPI()
    app.include_router(credits_router)
    app.add_exception_handler(IIAgentError, ii_agent_error_handler)

    app.dependency_overrides[get_current_user] = lambda: _make_user()
    app.dependency_overrides[_db_session_dependency] = lambda: AsyncMock()
    app.dependency_overrides[get_credit_service] = lambda: credit_service

    return app


def _make_credit_service_mock(
    *,
    balance=None,
    history_result=None,
    history_total: int = 0,
) -> MagicMock:
    svc = MagicMock()
    svc.get_balance = AsyncMock(return_value=balance)
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
    from datetime import datetime, timezone
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
    svc = _make_credit_service_mock(balance=balance, history_result=history, history_total=1)

    app = _build_credits_app(svc)
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
    svc = _make_credit_service_mock(balance=balance, history_result=[], history_total=0)

    app = _build_credits_app(svc)
    client = TestClient(app)
    resp = client.get("/credits/usage?page=2&per_page=5")

    assert resp.status_code == 200
    call_kwargs = svc.get_history.call_args.kwargs
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
    svc = _make_credit_service_mock(balance=balance, history_result=[], history_total=0)

    app = _build_credits_app(svc)
    client = TestClient(app)
    resp = client.get("/credits/usage")

    assert resp.status_code == 200
    data = resp.json()
    assert data["sessions"] == []
    assert data["total"] == 0
