"""Unit tests for CreditService ledger integration."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from ii_agent.billing.credits.ledger_repository import CreditLedgerRepository
from ii_agent.billing.credits.service import CreditDeductionResult, CreditService

pytestmark = pytest.mark.unit

_USER_ID = str(uuid.uuid4())


class FakeCreditBalanceRepo:
    def __init__(self, credits: float = 10.0, bonus_credits: float = 5.0):
        self.balances = {
            _USER_ID: SimpleNamespace(
                credits=Decimal(str(credits)),
                bonus_credits=Decimal(str(bonus_credits)),
                updated_at=datetime.now(timezone.utc),
            )
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
        return (bal.credits, bal.bonus_credits, bal.updated_at)

    async def check_sufficient(self, db, user_id, amount):
        bal = self.balances.get(user_id)
        if not bal:
            return False
        return (bal.credits + bal.bonus_credits) >= amount

    async def get_or_create(self, db, user_id, **kwargs):
        bal = self.balances.get(user_id)
        if bal:
            return (bal.credits, bal.bonus_credits, False)
        credits = Decimal(str(kwargs.get("credits", 0)))
        bonus = Decimal(str(kwargs.get("bonus_credits", 0)))
        self.balances[user_id] = SimpleNamespace(
            credits=credits, bonus_credits=bonus, updated_at=datetime.now(timezone.utc)
        )
        return (credits, bonus, True)

    async def deduct_credits(self, db, user_id, amount):
        bal = self.balances.get(user_id)
        if not bal:
            return None
        amount = Decimal(str(amount))
        total = bal.credits + bal.bonus_credits
        if total < amount:
            return None
        old_credits = bal.credits
        old_bonus = bal.bonus_credits
        bonus_used = min(bal.bonus_credits, amount)
        regular_used = amount - bonus_used
        bal.bonus_credits -= bonus_used
        bal.credits -= regular_used
        return old_credits, old_bonus, bal.credits, bal.bonus_credits

    async def _apply_deduction(self, db, user_id, amount):
        bal = self.balances.get(user_id)
        if not bal:
            return None
        amount = Decimal(str(amount))
        bonus_used = min(bal.bonus_credits, amount)
        regular_used = amount - bonus_used
        bal.bonus_credits -= bonus_used
        bal.credits -= regular_used
        return bal.credits, bal.bonus_credits

    async def add_credits(self, db, user_id, amount, is_bonus=False):
        bal = self.balances.get(user_id)
        if not bal:
            return None
        amount = Decimal(str(amount))
        old_credits = bal.credits
        old_bonus = bal.bonus_credits
        if is_bonus:
            bal.bonus_credits += amount
        else:
            bal.credits += amount
        return old_credits, old_bonus, bal.credits, bal.bonus_credits

    async def set_credits(self, db, user_id, amount, bonus_amount=None):
        bal = self.balances.get(user_id)
        if not bal:
            return None
        old_credits = bal.credits
        old_bonus = bal.bonus_credits
        bal.credits = Decimal(str(amount))
        if bonus_amount is not None:
            bal.bonus_credits = Decimal(str(bonus_amount))
        return old_credits, old_bonus, bal.credits, bal.bonus_credits


class FakeLedgerRepo:
    def __init__(self):
        self.entries: list[dict] = []

    async def append(self, db, **kwargs):
        self.entries.append(kwargs)
        return SimpleNamespace(id=len(self.entries), **kwargs)

    async def get_history(self, db, user_id, *, page=1, per_page=20):
        user_entries = [e for e in self.entries if e["user_id"] == user_id]
        return user_entries, len(user_entries)


def _make_service(balance_repo=None, ledger_repo=None) -> tuple[CreditService, FakeLedgerRepo]:
    lr = ledger_repo or FakeLedgerRepo()
    svc = CreditService(
        balance_repo=balance_repo or FakeCreditBalanceRepo(),
        ledger_repo=lr,
    )
    return svc, lr


class _FakeNestedTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


def _make_fake_db():
    """Return a minimal fake db supporting begin_nested()."""
    db = MagicMock()
    db.begin_nested.return_value = _FakeNestedTransaction()
    return db


# ---------------------------------------------------------------------------
# deduct appends ledger entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deduct_appends_ledger_entry():
    """Successful deduction appends a 'deduction' ledger entry."""
    svc, ledger = _make_service()

    result = await svc.deduct(_make_fake_db(), _USER_ID, 3.0)

    assert isinstance(result, CreditDeductionResult)
    assert result.total_charged == Decimal("3.0")
    assert len(ledger.entries) == 1
    entry = ledger.entries[0]
    assert entry["entry_type"] == "deduction"
    assert entry["user_id"] == _USER_ID
    # 3.0 deducted entirely from bonus (5.0), so regular credits unchanged
    assert float(entry["delta_credits"]) == 0.0
    assert float(entry["delta_bonus_credits"]) == -3.0


@pytest.mark.asyncio
async def test_deduct_no_ledger_on_failure():
    """Failed deduction does not append a ledger entry."""
    balance_repo = FakeCreditBalanceRepo(credits=1.0, bonus_credits=0.0)
    svc, ledger = _make_service(balance_repo=balance_repo)

    result = await svc.deduct(_make_fake_db(), _USER_ID, 10.0)

    assert result is False
    assert len(ledger.entries) == 0


@pytest.mark.asyncio
async def test_deduct_with_source_metadata():
    """Deduction passes source_domain and entry_metadata to ledger."""
    svc, ledger = _make_service()

    await svc.deduct(
        _make_fake_db(),
        _USER_ID,
        1.0,
        source_domain="llm_usage",
        source_id="sess-1",
        entry_metadata={"model_id": "claude-3"},
    )

    entry = ledger.entries[0]
    assert entry["source_domain"] == "llm_usage"
    assert entry["source_id"] == "sess-1"
    assert entry["entry_metadata"]["model_id"] == "claude-3"


# ---------------------------------------------------------------------------
# add appends ledger entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_regular_credits_appends_grant():
    """Regular credit addition appends a 'grant' entry with correct deltas."""
    svc, ledger = _make_service()

    await svc.add(_make_fake_db(), _USER_ID, 5.0)

    assert len(ledger.entries) == 1
    entry = ledger.entries[0]
    assert entry["entry_type"] == "grant"
    assert float(entry["delta_credits"]) == 5.0
    assert float(entry["delta_bonus_credits"]) == 0.0


@pytest.mark.asyncio
async def test_add_bonus_credits_appends_bonus_grant():
    """Bonus credit addition appends a 'bonus_grant' entry with correct deltas."""
    svc, ledger = _make_service()

    await svc.add(_make_fake_db(), _USER_ID, 3.0, is_bonus=True)

    entry = ledger.entries[0]
    assert entry["entry_type"] == "bonus_grant"
    assert float(entry["delta_credits"]) == 0.0
    assert float(entry["delta_bonus_credits"]) == 3.0


# ---------------------------------------------------------------------------
# set_balance appends ledger entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_balance_appends_plan_change_entry():
    """set_balance appends a ledger entry with correct delta."""
    db = _make_fake_db()
    svc, ledger = _make_service(balance_repo=FakeCreditBalanceRepo(credits=10.0, bonus_credits=5.0))

    await svc.set_balance(db, _USER_ID, 50.0, bonus_amount=10.0)

    assert len(ledger.entries) == 1
    entry = ledger.entries[0]
    assert entry["entry_type"] == "plan_change"
    # Delta should be 50 - 10 = 40
    assert float(entry["delta_credits"]) == 40.0
    # Bonus delta: 10 - 5 = 5
    assert float(entry["delta_bonus_credits"]) == 5.0


@pytest.mark.asyncio
async def test_set_balance_custom_entry_type():
    """set_balance can use a custom entry_type."""
    db = _make_fake_db()
    svc, ledger = _make_service()

    await svc.set_balance(
        db, _USER_ID, 100.0,
        entry_type="refresh",
        source_domain="cron",
    )

    entry = ledger.entries[0]
    assert entry["entry_type"] == "refresh"
    assert entry["source_domain"] == "cron"


# ---------------------------------------------------------------------------
# ensure_balance_exists writes initial_balance ledger entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_balance_exists_writes_initial_ledger_entry():
    """When ensure_balance_exists creates a new row with non-zero credits, a ledger entry is written."""
    svc, ledger = _make_service()
    new_user_id = str(uuid.uuid4())

    await svc.ensure_balance_exists(_make_fake_db(), new_user_id, credits=50.0, bonus_credits=10.0)

    assert len(ledger.entries) == 1
    entry = ledger.entries[0]
    assert entry["entry_type"] == "initial_balance"
    assert entry["user_id"] == new_user_id


@pytest.mark.asyncio
async def test_ensure_balance_exists_no_ledger_for_existing():
    """When ensure_balance_exists finds an existing row, no ledger entry is written."""
    svc, ledger = _make_service()

    await svc.ensure_balance_exists(_make_fake_db(), _USER_ID)

    assert len(ledger.entries) == 0


@pytest.mark.asyncio
async def test_ensure_balance_exists_no_ledger_when_race_lost():
    """When another request won the insert race, no duplicate ledger entry is written."""
    balance_repo = FakeCreditBalanceRepo()
    new_user_id = str(uuid.uuid4())

    # Simulate race: get_or_create returns created=False (another request won)
    async def _race_get_or_create(db, user_id, **kwargs):
        balance_repo.balances[user_id] = SimpleNamespace(
            credits=Decimal("100"), bonus_credits=Decimal("0"),
            updated_at=datetime.now(timezone.utc),
        )
        return (Decimal("100"), Decimal("0"), False)

    balance_repo.get_or_create = _race_get_or_create

    svc, ledger = _make_service(balance_repo=balance_repo)
    await svc.ensure_balance_exists(_make_fake_db(), new_user_id, credits=50.0, bonus_credits=10.0)

    assert len(ledger.entries) == 0


# ---------------------------------------------------------------------------
# get_ledger_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_ledger_history_returns_entries():
    """get_ledger_history returns paginated ledger entries."""
    svc, ledger = _make_service()

    # Add some entries
    await svc.deduct(_make_fake_db(), _USER_ID, 1.0)
    await svc.add(_make_fake_db(), _USER_ID, 5.0)

    entries, total = await svc.get_ledger_history(None, _USER_ID)

    assert total == 2
    assert len(entries) == 2


# ---------------------------------------------------------------------------
# deduct idempotency
# ---------------------------------------------------------------------------


class FakeLedgerRepoWithIdempotency(FakeLedgerRepo):
    """Ledger repo that simulates idempotency — returns None on duplicate keys."""

    def __init__(self):
        super().__init__()
        self._seen_keys: set[str] = set()

    async def append(self, db, **kwargs):
        key = kwargs.get("idempotency_key")
        if key and key in self._seen_keys:
            return None  # duplicate
        if key:
            self._seen_keys.add(key)
        return await super().append(db, **kwargs)


@pytest.mark.asyncio
async def test_deduct_idempotency_duplicate_returns_none():
    """Second deduction with same idempotency_key is a no-op that returns None."""
    ledger = FakeLedgerRepoWithIdempotency()
    svc, _ = _make_service(ledger_repo=ledger)
    db = _make_fake_db()

    result1 = await svc.deduct(db, _USER_ID, 2.0, idempotency_key="dup-key")
    result2 = await svc.deduct(db, _USER_ID, 2.0, idempotency_key="dup-key")

    assert isinstance(result1, CreditDeductionResult)
    assert result1.total_charged == Decimal("2.0")
    assert result2 is None
    # Only one ledger entry should exist
    assert len(ledger.entries) == 1


@pytest.mark.asyncio
async def test_deduct_idempotency_different_keys_both_succeed():
    """Different idempotency keys create separate ledger entries."""
    ledger = FakeLedgerRepoWithIdempotency()
    svc, _ = _make_service(ledger_repo=ledger)
    db = _make_fake_db()

    await svc.deduct(db, _USER_ID, 1.0, idempotency_key="key-a")
    await svc.deduct(db, _USER_ID, 1.0, idempotency_key="key-b")

    assert len(ledger.entries) == 2


# ---------------------------------------------------------------------------
# add idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_idempotency_duplicate_returns_none():
    """Second add with same idempotency_key is a no-op that returns None."""
    ledger = FakeLedgerRepoWithIdempotency()
    svc, _ = _make_service(ledger_repo=ledger)
    db = _make_fake_db()

    result1 = await svc.add(db, _USER_ID, 5.0, idempotency_key="add-dup")
    result2 = await svc.add(db, _USER_ID, 5.0, idempotency_key="add-dup")

    assert result1 is True
    assert result2 is None
    assert len(ledger.entries) == 1


@pytest.mark.asyncio
async def test_add_idempotency_different_keys_both_succeed():
    """Different idempotency keys on add create separate ledger entries."""
    ledger = FakeLedgerRepoWithIdempotency()
    svc, _ = _make_service(ledger_repo=ledger)
    db = _make_fake_db()

    await svc.add(db, _USER_ID, 5.0, idempotency_key="add-a")
    await svc.add(db, _USER_ID, 5.0, idempotency_key="add-b")

    assert len(ledger.entries) == 2


@pytest.mark.asyncio
async def test_add_without_idempotency_key_always_appends():
    """add without idempotency_key always creates a ledger entry."""
    svc, ledger = _make_service()
    db = _make_fake_db()

    await svc.add(db, _USER_ID, 1.0)
    await svc.add(db, _USER_ID, 1.0)

    assert len(ledger.entries) == 2


# ---------------------------------------------------------------------------
# set_balance idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_balance_idempotency_duplicate_returns_none():
    """Second set_balance with same idempotency_key is a no-op that returns None."""
    ledger = FakeLedgerRepoWithIdempotency()
    svc, _ = _make_service(ledger_repo=ledger)
    db = _make_fake_db()

    result1 = await svc.set_balance(db, _USER_ID, 50.0, idempotency_key="set-dup")
    result2 = await svc.set_balance(db, _USER_ID, 50.0, idempotency_key="set-dup")

    assert result1 is True
    assert result2 is None
    assert len(ledger.entries) == 1


@pytest.mark.asyncio
async def test_set_balance_idempotency_different_keys_both_succeed():
    """Different idempotency keys on set_balance create separate ledger entries."""
    ledger = FakeLedgerRepoWithIdempotency()
    svc, _ = _make_service(ledger_repo=ledger)
    db = _make_fake_db()

    await svc.set_balance(db, _USER_ID, 50.0, idempotency_key="set-a")
    await svc.set_balance(db, _USER_ID, 100.0, idempotency_key="set-b")

    assert len(ledger.entries) == 2


@pytest.mark.asyncio
async def test_set_balance_without_idempotency_key_always_appends():
    """set_balance without idempotency_key always creates a ledger entry."""
    svc, ledger = _make_service()
    db = _make_fake_db()

    await svc.set_balance(db, _USER_ID, 50.0)
    await svc.set_balance(db, _USER_ID, 50.0)

    assert len(ledger.entries) == 2


# ---------------------------------------------------------------------------
# deduct edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deduct_exact_balance():
    """Deducting exactly the total balance succeeds and zeroes out."""
    balance_repo = FakeCreditBalanceRepo(credits=7.0, bonus_credits=3.0)
    svc, ledger = _make_service(balance_repo=balance_repo)

    result = await svc.deduct(_make_fake_db(), _USER_ID, 10.0)

    assert isinstance(result, CreditDeductionResult)
    assert result.total_charged == Decimal("10.0")
    assert balance_repo.balances[_USER_ID].credits == Decimal("0")
    assert balance_repo.balances[_USER_ID].bonus_credits == Decimal("0")
    entry = ledger.entries[0]
    assert float(entry["delta_bonus_credits"]) == -3.0
    assert float(entry["delta_credits"]) == -7.0


@pytest.mark.asyncio
async def test_deduct_splits_across_bonus_and_regular():
    """Deduction larger than bonus spills into regular credits with correct ledger."""
    balance_repo = FakeCreditBalanceRepo(credits=20.0, bonus_credits=3.0)
    svc, ledger = _make_service(balance_repo=balance_repo)

    result = await svc.deduct(_make_fake_db(), _USER_ID, 8.0)

    assert isinstance(result, CreditDeductionResult)
    assert result.total_charged == Decimal("8.0")
    entry = ledger.entries[0]
    assert float(entry["delta_bonus_credits"]) == -3.0
    assert float(entry["delta_credits"]) == -5.0


# ---------------------------------------------------------------------------
# ensure_balance_exists edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_balance_exists_no_ledger_for_zero_credits():
    """When ensure_balance_exists creates with zero credits, no ledger entry."""
    svc, ledger = _make_service()
    new_user_id = str(uuid.uuid4())

    await svc.ensure_balance_exists(_make_fake_db(), new_user_id, credits=0, bonus_credits=0)

    assert len(ledger.entries) == 0


# ---------------------------------------------------------------------------
# set_balance ledger delta verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_balance_decrease_records_negative_delta():
    """set_balance to a lower amount records negative delta in ledger."""
    db = _make_fake_db()
    svc, ledger = _make_service(
        balance_repo=FakeCreditBalanceRepo(credits=100.0, bonus_credits=20.0)
    )

    await svc.set_balance(db, _USER_ID, 30.0, bonus_amount=5.0)

    entry = ledger.entries[0]
    assert float(entry["delta_credits"]) == -70.0
    assert float(entry["delta_bonus_credits"]) == -15.0


@pytest.mark.asyncio
async def test_set_balance_same_values_records_zero_delta():
    """set_balance to same values records zero deltas."""
    db = _make_fake_db()
    svc, ledger = _make_service(
        balance_repo=FakeCreditBalanceRepo(credits=10.0, bonus_credits=5.0)
    )

    await svc.set_balance(db, _USER_ID, 10.0, bonus_amount=5.0)

    entry = ledger.entries[0]
    assert float(entry["delta_credits"]) == 0.0
    assert float(entry["delta_bonus_credits"]) == 0.0


@pytest.mark.asyncio
async def test_ledger_repo_targets_partial_idempotency_index():
    """PostgreSQL SQL should infer the partial unique index on idempotency_key."""
    repo = CreditLedgerRepository()
    captured = {}

    class _FakeResult:
        def first(self):
            return None

    class _FakeDB:
        async def execute(self, stmt):
            captured["sql"] = str(
                stmt.compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            )
            return _FakeResult()

        async def flush(self):
            return None

    result = await repo._append_idempotent(
        _FakeDB(),
        user_id=_USER_ID,
        entry_type="deduction",
        source_domain="llm_usage",
        source_id="sess-1",
        delta_credits=Decimal("-1.0"),
        delta_bonus_credits=Decimal("0"),
        balance_after_credits=Decimal("9.0"),
        balance_after_bonus_credits=Decimal("5.0"),
        entry_metadata=None,
        idempotency_key="idem-1",
    )

    assert result is None
    assert (
        "ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING"
        in captured["sql"]
    )
