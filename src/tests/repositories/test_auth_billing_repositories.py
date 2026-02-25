from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.auth.models import WaitlistEntry
from ii_agent.auth.users.repository import APIKeyRepository, UserRepository
from ii_agent.auth.users.waitlist_repository import WaitlistRepository
from ii_agent.billing.repository import BillingTransactionRepository
from ii_agent.billing.usage.repository import MetricsRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_user_and_api_key_repositories_crud_and_credit_updates(
    db_session: AsyncSession,
) -> None:
    user_repo = UserRepository()
    api_key_repo = APIKeyRepository()

    user = await user_repo.create(
        db_session,
        email="CaseSensitive@Example.com",
        first_name="Case",
        credits=10.0,
        bonus_credits=5.0,
    )

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
    await user_repo.update_subscription(
        db_session,
        user,
        subscription_plan="plus",
        subscription_status="active",
        subscription_billing_cycle="monthly",
        stripe_customer_id="cus_123",
        subscription_current_period_end=datetime.now(timezone.utc),
    )
    await user_repo.set_language(db_session, user, "vi")
    await user_repo.set_active(db_session, user, is_active=False)

    credits_after_deduct = await user_repo.deduct_credits(db_session, user.id, 6.0)
    assert credits_after_deduct == (9.0, 0.0)

    credits_after_bonus = await user_repo.add_credits(
        db_session, user.id, 2.0, is_bonus=True
    )
    assert credits_after_bonus == (9.0, 2.0)

    exact_credits = await user_repo.set_credits(
        db_session, user.id, 42.0, bonus_amount=3.5
    )
    assert exact_credits == (42.0, 3.5)

    api_key = await api_key_repo.create(
        db_session,
        user_id=user.id,
        api_key="sk-test-123",
    )
    assert api_key.user_id == user.id

    active_key = await api_key_repo.get_active_for_user(db_session, user.id)
    assert active_key == "sk-test-123"

    customer_user_id = await user_repo.lookup_by_customer_id(db_session, "cus_123")
    assert customer_user_id == user.id


async def test_user_repository_optional_branches_and_not_found_paths(
    db_session: AsyncSession,
) -> None:
    repo = UserRepository()
    api_key_repo = APIKeyRepository()
    user = await repo.create(
        db_session,
        email="branches@example.com",
        first_name="Before",
        credits=5.0,
        bonus_credits=2.0,
    )

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

    await repo.update_subscription(
        db_session,
        user,
        subscription_billing_cycle=None,
        credits=11.5,
    )
    assert user.subscription_billing_cycle is None
    assert user.credits == 11.5

    await repo.update_subscription(db_session, user)
    assert user.subscription_billing_cycle is None

    regular_credit_update = await repo.add_credits(db_session, user.id, 3.0, is_bonus=False)
    assert regular_credit_update == (14.5, 2.0)

    no_bonus_override = await repo.set_credits(db_session, user.id, 9.0)
    assert no_bonus_override == (9.0, 2.0)

    assert await repo.deduct_credits(db_session, user.id, 1000.0) is None
    assert await repo.lookup_by_customer_id(db_session, "missing-customer") is None
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


async def test_metrics_repository_create_get_and_unique_session_constraint(
    db_session: AsyncSession,
    session_factory,
) -> None:
    session = await session_factory()
    repo = MetricsRepository()

    created = await repo.create(db_session, session.id, 1.25)
    fetched = await repo.get_by_session_id(db_session, session.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.credits == 1.25

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await repo.create(db_session, session.id, 2.0)


async def test_waitlist_repository_case_insensitive_lookup(
    db_session: AsyncSession,
) -> None:
    repo = WaitlistRepository()
    db_session.add(WaitlistEntry(email="Person@Example.com"))
    await db_session.flush()

    found = await repo.get_by_email(db_session, "person@example.com")
    assert found is not None
    assert found.email == "Person@Example.com"
