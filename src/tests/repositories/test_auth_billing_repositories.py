from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.users.models import WaitlistEntry
from ii_agent.users.repository import APIKeyRepository, UserRepository
from ii_agent.users.waitlist_repository import WaitlistRepository
from ii_agent.credits.repository import CreditBalanceRepository

try:
    from ii_agent.billing.repository import BillingTransactionRepository
except ImportError:
    BillingTransactionRepository = None  # type: ignore[misc, assignment]

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_user_and_api_key_repositories_crud_and_credit_updates(
    db_session: AsyncSession,
) -> None:
    user_repo = UserRepository()
    api_key_repo = APIKeyRepository()
    balance_repo = CreditBalanceRepository()

    user = await user_repo.create(
        db_session,
        email="CaseSensitive@Example.com",
        first_name="Case",
        credits=10.0,
        bonus_credits=5.0,
    )
    # Create matching credit_balances row
    await balance_repo.create(db_session, user.id, credits=10.0, bonus_credits=5.0)

    lookup = await user_repo.get_by_email(db_session, "casesensitive@example.com")
    assert lookup is not None
    assert lookup.id == user.id

    await user_repo.update_profile(
        db_session,
        user,
        last_name="User",
        email_verified=True,
        avatar="https://img.local/avatar.png",
    )
    await user_repo.set_language(db_session, user, "vi")
    await user_repo.set_active(db_session, user, is_active=False)

    # Credit operations now go through CreditBalanceRepository
    # All methods accept and return Decimal; compare with float() for readability
    credits_after_deduct = await balance_repo.deduct_credits(db_session, user.id, Decimal("6.0"))
    # Returns (old_credits, old_bonus, new_credits, new_bonus)
    # Created with credits=10.0, bonus_credits=5.0; deducting 6.0 uses 5.0 bonus + 1.0 regular
    assert tuple(float(v) for v in credits_after_deduct) == (10.0, 5.0, 9.0, 0.0)

    credits_after_bonus = await balance_repo.add_credits(
        db_session, user.id, Decimal("2.0"), is_bonus=True
    )
    # Returns (old_credits, old_bonus, new_credits, new_bonus)
    assert tuple(float(v) for v in credits_after_bonus) == (9.0, 0.0, 9.0, 2.0)

    exact_credits = await balance_repo.set_credits(
        db_session, user.id, Decimal("42.0"), bonus_amount=Decimal("3.5")
    )
    # Returns (old_credits, old_bonus, new_credits, new_bonus)
    assert tuple(float(v) for v in exact_credits) == (9.0, 2.0, 42.0, 3.5)

    api_key = await api_key_repo.create(
        db_session,
        user_id=user.id,
        api_key="sk-test-123",
    )
    assert api_key.user_id == user.id

    active_key = await api_key_repo.get_active_for_user(db_session, user.id)
    assert active_key == "sk-test-123"


async def test_user_repository_optional_branches_and_not_found_paths(
    db_session: AsyncSession,
) -> None:
    repo = UserRepository()
    api_key_repo = APIKeyRepository()
    balance_repo = CreditBalanceRepository()
    user = await repo.create(
        db_session,
        email="branches@example.com",
        first_name="Before",
        credits=5.0,
        bonus_credits=2.0,
    )
    # Create matching credit_balances row
    await balance_repo.create(db_session, user.id, credits=5.0, bonus_credits=2.0)

    loaded = await repo.get_by_id(db_session, user.id)
    assert loaded is not None
    assert await repo.get_by_id(db_session, "missing-user-id") is None

    await repo.update_fields(
        db_session,
        user,
        first_name="After",
        avatar=None,
    )
    assert user.first_name == "After"
    assert user.avatar is None

    await repo.update_profile(
        db_session,
        user,
        login_provider="google",
        email_verified=False,
    )
    assert user.login_provider == "google"
    assert user.email_verified is False
    await repo.update_profile(
        db_session,
        user,
        first_name="Final Name",
    )
    assert user.first_name == "Final Name"

    # Credit operations now go through CreditBalanceRepository
    regular_credit_update = await balance_repo.add_credits(
        db_session, user.id, Decimal("3.0"), is_bonus=False
    )
    # Returns (old_credits, old_bonus, new_credits, new_bonus)
    assert tuple(float(v) for v in regular_credit_update) == (5.0, 2.0, 8.0, 2.0)

    no_bonus_override = await balance_repo.set_credits(db_session, user.id, Decimal("9.0"))
    # Returns (old_credits, old_bonus, new_credits, new_bonus)
    assert tuple(float(v) for v in no_bonus_override) == (8.0, 2.0, 9.0, 2.0)

    assert await balance_repo.deduct_credits(db_session, user.id, Decimal("1000.0")) is None
    assert await api_key_repo.get_active_for_user(db_session, user.id) is None


async def test_user_repository_uniqueness_conflict_rolls_back_savepoint(
    db_session: AsyncSession,
) -> None:
    repo = UserRepository()
    created = await repo.create(db_session, email="dupe@example.com", credits=5.0)
    assert created.email == "dupe@example.com"

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await repo.create(db_session, email="dupe@example.com", credits=1.0)

    still_present = await repo.get_by_email(db_session, "dupe@example.com")
    assert still_present is not None
    assert still_present.id == created.id


@pytest.mark.skipif(
    BillingTransactionRepository is None, reason="BillingTransactionRepository removed"
)
async def test_billing_transaction_repository_create_lookup_and_conflict(
    db_session: AsyncSession,
    user_factory,
) -> None:
    user = await user_factory()
    repo = BillingTransactionRepository()

    transaction = await repo.create(
        db_session,
        user_id=user.id,
        stripe_event_id="evt_1",
        status="paid",
        amount=15.0,
        currency="usd",
    )
    fetched = await repo.get_by_event_id(db_session, "evt_1")
    assert fetched is not None
    assert fetched.id == transaction.id

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await repo.create(
                db_session,
                user_id=user.id,
                stripe_event_id="evt_1",
                status="paid",
            )


async def test_waitlist_repository_case_insensitive_lookup(
    db_session: AsyncSession,
) -> None:
    repo = WaitlistRepository()
    db_session.add(WaitlistEntry(email="Person@Example.com"))
    await db_session.flush()

    found = await repo.get_by_email(db_session, "person@example.com")
    assert found is not None
    assert found.email == "Person@Example.com"
