from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ii_agent.billing.credits.service import CreditService


class FakeUserRepo:
    def __init__(self):
        self.users = {
            "u1": SimpleNamespace(id="u1", credits=10.0, bonus_credits=5.0)
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


@pytest.mark.asyncio
async def test_credit_arithmetic_deduct_add_set_balance():
    service = CreditService(user_repo=FakeUserRepo(), metrics_repo=FakeMetricsRepo())

    assert await service.deduct(None, "u1", 6.0) is True
    assert service._user_repo.users["u1"].bonus_credits == 0.0
    assert service._user_repo.users["u1"].credits == 9.0

    assert await service.add(None, "u1", 2.0, is_bonus=True) is True
    assert service._user_repo.users["u1"].bonus_credits == 2.0

    assert await service.set_balance(None, "u1", 20.0, bonus_amount=3.0) is True
    assert service._user_repo.users["u1"].credits == 20.0
    assert service._user_repo.users["u1"].bonus_credits == 3.0


@pytest.mark.asyncio
async def test_has_sufficient_uses_regular_plus_bonus(monkeypatch):
    service = CreditService(user_repo=FakeUserRepo(), metrics_repo=FakeMetricsRepo())

    async def _fake_balance(db, user_id):
        return SimpleNamespace(credits=1.0, bonus_credits=2.0)

    monkeypatch.setattr(service, "get_balance", _fake_balance)

    assert await service.has_sufficient(None, "u1", 3.0) is True
    assert await service.has_sufficient(None, "u1", 3.1) is False


@pytest.mark.asyncio
async def test_accumulate_session_usage_creates_and_updates_metrics():
    metrics_repo = FakeMetricsRepo()
    service = CreditService(user_repo=FakeUserRepo(), metrics_repo=metrics_repo)

    await service.accumulate_session_usage(None, "s1", -1.0)
    await service.accumulate_session_usage(None, "s1", -2.0)

    assert metrics_repo.records["s1"].credits == -3.0
