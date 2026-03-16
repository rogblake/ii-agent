"""Unit tests for CreditBalanceRepository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.billing.credits.balance_repository import CreditBalanceRepository

pytestmark = pytest.mark.unit

_USER_ID = str(uuid.uuid4())


def _make_repo() -> CreditBalanceRepository:
    return CreditBalanceRepository()


# ---------------------------------------------------------------------------
# get_balance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_balance_returns_tuple():
    """get_balance returns (credits, bonus_credits) when row exists."""
    repo = _make_repo()

    async def _exec(stmt):
        row = SimpleNamespace(credits=Decimal("10.5"), bonus_credits=Decimal("3.0"))
        return SimpleNamespace(first=lambda: row)

    db = SimpleNamespace(execute=_exec)
    result = await repo.get_balance(db, _USER_ID)
    assert result == (Decimal("10.5"), Decimal("3.0"))


@pytest.mark.asyncio
async def test_get_balance_returns_none_when_missing():
    """get_balance returns None when no row found."""
    repo = _make_repo()

    async def _exec(stmt):
        return SimpleNamespace(first=lambda: None)

    db = SimpleNamespace(execute=_exec)
    result = await repo.get_balance(db, "ghost")
    assert result is None


# ---------------------------------------------------------------------------
# get_balance_with_updated_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_balance_with_updated_at_returns_triple():
    """get_balance_with_updated_at returns (credits, bonus_credits, updated_at)."""
    repo = _make_repo()
    now = datetime.now(timezone.utc)

    async def _exec(stmt):
        row = SimpleNamespace(
            credits=Decimal("10.0"), bonus_credits=Decimal("3.0"), updated_at=now
        )
        return SimpleNamespace(first=lambda: row)

    db = SimpleNamespace(execute=_exec)
    result = await repo.get_balance_with_updated_at(db, _USER_ID)
    assert result == (Decimal("10.0"), Decimal("3.0"), now)


@pytest.mark.asyncio
async def test_get_balance_with_updated_at_returns_none():
    """get_balance_with_updated_at returns None when missing."""
    repo = _make_repo()

    async def _exec(stmt):
        return SimpleNamespace(first=lambda: None)

    db = SimpleNamespace(execute=_exec)
    assert await repo.get_balance_with_updated_at(db, "ghost") is None


# ---------------------------------------------------------------------------
# deduct_credits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deduct_credits_returns_old_and_new():
    """deduct_credits returns (old_credits, old_bonus, new_credits, new_bonus) as Decimal."""
    repo = _make_repo()
    call_count = 0

    async def _exec(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # SELECT ... FOR UPDATE (old values)
            row = SimpleNamespace(credits=Decimal("10.0"), bonus_credits=Decimal("0.0"))
            return SimpleNamespace(first=lambda: row)
        # UPDATE ... RETURNING (new values)
        row = SimpleNamespace(credits=Decimal("7.0"), bonus_credits=Decimal("0.0"))
        return SimpleNamespace(first=lambda: row)

    db = SimpleNamespace(execute=_exec)
    result = await repo.deduct_credits(db, _USER_ID, Decimal("3.0"))
    assert result == (Decimal("10.0"), Decimal("0.0"), Decimal("7.0"), Decimal("0.0"))


@pytest.mark.asyncio
async def test_deduct_credits_returns_none_when_no_row():
    """deduct_credits returns None when user has no balance row."""
    repo = _make_repo()

    async def _exec(stmt):
        return SimpleNamespace(first=lambda: None)

    db = SimpleNamespace(execute=_exec)
    result = await repo.deduct_credits(db, _USER_ID, Decimal("999.0"))
    assert result is None


@pytest.mark.asyncio
async def test_deduct_credits_returns_none_insufficient():
    """deduct_credits returns None when balance is insufficient."""
    repo = _make_repo()

    async def _exec(stmt):
        # SELECT ... FOR UPDATE returns a row with insufficient balance
        row = SimpleNamespace(credits=Decimal("1.0"), bonus_credits=Decimal("0.5"))
        return SimpleNamespace(first=lambda: row)

    db = SimpleNamespace(execute=_exec)
    result = await repo.deduct_credits(db, _USER_ID, Decimal("999.0"))
    assert result is None


# ---------------------------------------------------------------------------
# add_credits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_credits_regular():
    """add_credits with is_bonus=False returns (old, old, new, new) as Decimal."""
    repo = _make_repo()
    call_count = 0

    async def _exec(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # SELECT ... FOR UPDATE (old values)
            row = SimpleNamespace(credits=Decimal("10.0"), bonus_credits=Decimal("5.0"))
            return SimpleNamespace(first=lambda: row)
        # UPDATE ... RETURNING (new values)
        row = SimpleNamespace(credits=Decimal("15.0"), bonus_credits=Decimal("5.0"))
        return SimpleNamespace(first=lambda: row)

    db = SimpleNamespace(execute=_exec)
    result = await repo.add_credits(db, _USER_ID, Decimal("5.0"))
    assert result == (Decimal("10.0"), Decimal("5.0"), Decimal("15.0"), Decimal("5.0"))


@pytest.mark.asyncio
async def test_add_credits_bonus():
    """add_credits with is_bonus=True returns (old, old, new, new) as Decimal."""
    repo = _make_repo()
    call_count = 0

    async def _exec(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # SELECT ... FOR UPDATE (old values)
            row = SimpleNamespace(credits=Decimal("10.0"), bonus_credits=Decimal("5.0"))
            return SimpleNamespace(first=lambda: row)
        # UPDATE ... RETURNING (new values)
        row = SimpleNamespace(credits=Decimal("10.0"), bonus_credits=Decimal("8.0"))
        return SimpleNamespace(first=lambda: row)

    db = SimpleNamespace(execute=_exec)
    result = await repo.add_credits(db, _USER_ID, Decimal("3.0"), is_bonus=True)
    assert result == (Decimal("10.0"), Decimal("5.0"), Decimal("10.0"), Decimal("8.0"))


@pytest.mark.asyncio
async def test_add_credits_returns_none_missing():
    """add_credits returns None when user not found."""
    repo = _make_repo()

    async def _exec(stmt):
        return SimpleNamespace(first=lambda: None)

    db = SimpleNamespace(execute=_exec)
    result = await repo.add_credits(db, "ghost", Decimal("5.0"))
    assert result is None


# ---------------------------------------------------------------------------
# set_credits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_credits_returns_old_and_new():
    """set_credits returns (old_credits, old_bonus, new_credits, new_bonus) as Decimal."""
    repo = _make_repo()
    call_count = 0

    async def _exec(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # SELECT ... FOR UPDATE (old values)
            row = SimpleNamespace(credits=Decimal("10.0"), bonus_credits=Decimal("5.0"))
            return SimpleNamespace(first=lambda: row)
        # UPDATE ... RETURNING (new values)
        row = SimpleNamespace(credits=Decimal("50.0"), bonus_credits=Decimal("10.0"))
        return SimpleNamespace(first=lambda: row)

    db = SimpleNamespace(execute=_exec)
    result = await repo.set_credits(db, _USER_ID, Decimal("50.0"), bonus_amount=Decimal("10.0"))
    assert result == (Decimal("10.0"), Decimal("5.0"), Decimal("50.0"), Decimal("10.0"))


@pytest.mark.asyncio
async def test_set_credits_without_bonus():
    """set_credits without bonus_amount only sets regular credits."""
    repo = _make_repo()
    call_count = 0

    async def _exec(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            row = SimpleNamespace(credits=Decimal("10.0"), bonus_credits=Decimal("5.0"))
            return SimpleNamespace(first=lambda: row)
        row = SimpleNamespace(credits=Decimal("100.0"), bonus_credits=Decimal("5.0"))
        return SimpleNamespace(first=lambda: row)

    db = SimpleNamespace(execute=_exec)
    result = await repo.set_credits(db, _USER_ID, Decimal("100.0"))
    assert result == (Decimal("10.0"), Decimal("5.0"), Decimal("100.0"), Decimal("5.0"))


@pytest.mark.asyncio
async def test_set_credits_returns_none_missing():
    """set_credits returns None when user not found."""
    repo = _make_repo()

    async def _exec(stmt):
        return SimpleNamespace(first=lambda: None)

    db = SimpleNamespace(execute=_exec)
    result = await repo.set_credits(db, "ghost", Decimal("10.0"))
    assert result is None


# ---------------------------------------------------------------------------
# get_or_create
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# check_sufficient
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_sufficient_returns_true():
    """check_sufficient returns True when total balance >= amount."""
    repo = _make_repo()

    async def _exec(stmt):
        return SimpleNamespace(scalar=lambda: True)

    db = SimpleNamespace(execute=_exec)
    result = await repo.check_sufficient(db, _USER_ID, Decimal("10.0"))
    assert result is True


@pytest.mark.asyncio
async def test_check_sufficient_returns_false():
    """check_sufficient returns False when total balance < amount."""
    repo = _make_repo()

    async def _exec(stmt):
        return SimpleNamespace(scalar=lambda: False)

    db = SimpleNamespace(execute=_exec)
    result = await repo.check_sufficient(db, _USER_ID, Decimal("999.0"))
    assert result is False


@pytest.mark.asyncio
async def test_check_sufficient_returns_false_when_no_row():
    """check_sufficient returns False when user has no balance row."""
    repo = _make_repo()

    async def _exec(stmt):
        return SimpleNamespace(scalar=lambda: None)

    db = SimpleNamespace(execute=_exec)
    result = await repo.check_sufficient(db, "ghost", Decimal("1.0"))
    assert result is False


# ---------------------------------------------------------------------------
# lock_balance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lock_balance_returns_tuple():
    """lock_balance returns (credits, bonus_credits) when row exists."""
    repo = _make_repo()

    async def _exec(stmt):
        row = SimpleNamespace(credits=Decimal("10.0"), bonus_credits=Decimal("5.0"))
        return SimpleNamespace(first=lambda: row)

    db = SimpleNamespace(execute=_exec)
    result = await repo.lock_balance(db, _USER_ID)
    assert result == (Decimal("10.0"), Decimal("5.0"))


@pytest.mark.asyncio
async def test_lock_balance_returns_none_when_missing():
    """lock_balance returns None when no row found."""
    repo = _make_repo()

    async def _exec(stmt):
        return SimpleNamespace(first=lambda: None)

    db = SimpleNamespace(execute=_exec)
    result = await repo.lock_balance(db, "ghost")
    assert result is None


# ---------------------------------------------------------------------------
# get_or_create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_create_returns_existing():
    """get_or_create returns existing balance when row already exists."""
    repo = _make_repo()

    async def _exec(stmt):
        # get_balance SELECT returns existing row
        row = SimpleNamespace(credits=Decimal("10.0"), bonus_credits=Decimal("5.0"))
        return SimpleNamespace(first=lambda: row)

    db = SimpleNamespace(execute=_exec)
    result = await repo.get_or_create(db, _USER_ID)
    assert result == (Decimal("10.0"), Decimal("5.0"), False)


@pytest.mark.asyncio
async def test_get_or_create_creates_when_missing():
    """get_or_create inserts via ON CONFLICT DO NOTHING when no row exists."""
    repo = _make_repo()

    # First call to get_balance returns None (no row), second returns the new row
    repo.get_balance = AsyncMock(
        side_effect=[None, (Decimal("25.0"), Decimal("5.0"))]
    )

    db = AsyncMock()
    db.bind.dialect.name = "postgresql"
    # pg_insert ... RETURNING gives back a row when the insert succeeds
    db.execute = AsyncMock(
        return_value=SimpleNamespace(first=lambda: SimpleNamespace(user_id=_USER_ID))
    )
    result = await repo.get_or_create(db, _USER_ID, credits=25.0, bonus_credits=5.0)
    assert result == (Decimal("25.0"), Decimal("5.0"), True)
    db.execute.assert_called_once()
