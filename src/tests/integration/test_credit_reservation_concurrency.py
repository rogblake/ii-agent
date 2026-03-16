"""PostgreSQL-backed concurrency coverage for reservation locking."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, func, insert, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ii_agent.auth.users.models import User
from ii_agent.billing.credits.balance_models import CreditBalanceRecord
from ii_agent.billing.credits.balance_repository import CreditBalanceRepository
from ii_agent.billing.credits.ledger_models import CreditLedgerEntry
from ii_agent.billing.credits.ledger_repository import CreditLedgerRepository
from ii_agent.billing.exceptions import InsufficientCreditsError
from ii_agent.billing.reservations.models import CreditReservation
from ii_agent.billing.reservations.repository import CreditReservationRepository
from ii_agent.billing.reservations.service import CreditReservationService
from ii_agent.billing.reservations.types import BillingQuote, ReservationStatus
from ii_agent.billing.usage.models import UsageRecord
from ii_agent.core.config.settings import get_settings
from ii_agent.core.db.base import Base

pytestmark = [pytest.mark.integration, pytest.mark.external]


class _NoopCreditService:
    async def deduct(self, db, user_id, amount, **kwargs):
        raise AssertionError("shortfall billing should not run in these tests")


class _RecordingUsageService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def record_settled_usage(self, db, **kwargs):
        self.calls.append(kwargs)
        return 101


class _BlockingBalanceRepository(CreditBalanceRepository):
    def __init__(self) -> None:
        super().__init__()
        self.first_lock_acquired = asyncio.Event()
        self.release_first_lock = asyncio.Event()
        self._did_block = False

    async def lock_balance_state(self, db, user_id):
        result = await super().lock_balance_state(db, user_id)
        if not self._did_block:
            self._did_block = True
            self.first_lock_acquired.set()
            await self.release_first_lock.wait()
        return result


class _BlockingReservationRepository(CreditReservationRepository):
    def __init__(self) -> None:
        super().__init__()
        self.first_lock_acquired = asyncio.Event()
        self.release_first_lock = asyncio.Event()
        self._did_block = False

    async def lock_by_id(self, db, reservation_id):
        result = await super().lock_by_id(db, reservation_id)
        if not self._did_block:
            self._did_block = True
            self.first_lock_acquired.set()
            await self.release_first_lock.wait()
        return result


@dataclass
class _ReservationDbHarness:
    session_factory: async_sessionmaker
    async_engine: object
    sync_engine: object
    schema: str


@pytest_asyncio.fixture
async def reservation_db():
    pytest.importorskip("asyncpg")

    settings = get_settings()
    sync_url = settings.sync_database_url
    async_url = settings.database.url or sync_url
    if not sync_url.startswith("postgresql://"):
        pytest.skip("Reservation concurrency tests require PostgreSQL")
    if async_url.startswith("postgresql://"):
        async_url = async_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    schema = f"test_credit_reservation_concurrency_{uuid4().hex[:8]}"
    sync_engine = create_engine(sync_url, isolation_level="AUTOCOMMIT", future=True)

    try:
        with sync_engine.connect() as connection:
            connection.execute(text(f"CREATE SCHEMA {schema}"))
    except OperationalError as exc:  # pragma: no cover - depends on external DB
        sync_engine.dispose()
        pytest.skip(f"PostgreSQL test database unavailable: {exc}")

    async_engine = create_async_engine(
        async_url,
        connect_args={"server_settings": {"search_path": f"{schema},public"}},
        future=True,
    )

    try:
        async with async_engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn,
                    tables=[
                        User.__table__,
                        CreditBalanceRecord.__table__,
                        CreditLedgerEntry.__table__,
                        UsageRecord.__table__,
                        CreditReservation.__table__,
                    ],
                )
            )
    except OperationalError as exc:  # pragma: no cover - depends on external DB
        await async_engine.dispose()
        with suppress(Exception):
            with sync_engine.connect() as connection:
                connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        sync_engine.dispose()
        pytest.skip(f"PostgreSQL test database unavailable: {exc}")

    session_factory = async_sessionmaker(
        bind=async_engine,
        expire_on_commit=False,
        autoflush=False,
    )

    harness = _ReservationDbHarness(
        session_factory=session_factory,
        async_engine=async_engine,
        sync_engine=sync_engine,
        schema=schema,
    )
    try:
        yield harness
    finally:
        await async_engine.dispose()
        with suppress(Exception):
            with sync_engine.connect() as connection:
                connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        sync_engine.dispose()


async def _seed_user_with_balance(
    session_factory: async_sessionmaker,
    *,
    user_id: str,
    credits: Decimal,
    bonus_credits: Decimal = Decimal("0"),
) -> None:
    async with session_factory() as session:
        await session.execute(
            insert(User).values(
                id=user_id,
                email=f"{user_id}@example.com",
            )
        )
        await CreditBalanceRepository().create(
            session,
            user_id=user_id,
            credits=credits,
            bonus_credits=bonus_credits,
        )
        await session.commit()


def _make_service(
    *,
    balance_repo: CreditBalanceRepository | None = None,
    reservation_repo: CreditReservationRepository | None = None,
    usage_service: _RecordingUsageService | None = None,
) -> CreditReservationService:
    return CreditReservationService(
        balance_repo=balance_repo or CreditBalanceRepository(),
        ledger_repo=CreditLedgerRepository(),
        reservation_repo=reservation_repo or CreditReservationRepository(),
        credit_service=_NoopCreditService(),
        usage_service=usage_service or _RecordingUsageService(),
    )


@pytest.mark.asyncio
async def test_concurrent_reserves_allow_only_one_hold(reservation_db):
    user_id = "reserve-race-user"
    await _seed_user_with_balance(
        reservation_db.session_factory,
        user_id=user_id,
        credits=Decimal("1"),
    )

    balance_repo = _BlockingBalanceRepository()
    service = _make_service(balance_repo=balance_repo)
    quote = BillingQuote(
        strategy="bounded",
        reserve_usd=Decimal("0.015"),
        max_usd=Decimal("0.015"),
    )
    second_started = asyncio.Event()

    async def _reserve(idempotency_key: str, source_id: str):
        async with reservation_db.session_factory() as session:
            try:
                if source_id == "call-2":
                    second_started.set()
                hold = await service.reserve(
                    session,
                    user_id=user_id,
                    source_domain="chat_llm",
                    source_id=source_id,
                    billing_kind="llm_usage",
                    quote=quote,
                    idempotency_key=idempotency_key,
                )
                await session.commit()
                return SimpleNamespace(ok=True, hold=hold, error=None)
            except Exception as exc:
                await session.rollback()
                return SimpleNamespace(ok=False, hold=None, error=exc)

    first_task = asyncio.create_task(_reserve("reserve-race-1", "call-1"))
    await asyncio.wait_for(balance_repo.first_lock_acquired.wait(), timeout=5)

    second_task = asyncio.create_task(_reserve("reserve-race-2", "call-2"))
    await asyncio.wait_for(second_started.wait(), timeout=5)
    await asyncio.sleep(0.1)
    assert not second_task.done()

    balance_repo.release_first_lock.set()
    first_result, second_result = await asyncio.wait_for(
        asyncio.gather(first_task, second_task),
        timeout=5,
    )

    successes = [result for result in (first_result, second_result) if result.ok]
    failures = [result for result in (first_result, second_result) if not result.ok]

    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0].error, InsufficientCreditsError)

    async with reservation_db.session_factory() as session:
        credits, bonus_credits = (
            await session.execute(
                select(
                    CreditBalanceRecord.credits,
                    CreditBalanceRecord.bonus_credits,
                ).where(CreditBalanceRecord.user_id == user_id)
            )
        ).one()
        reservation_count = (
            await session.execute(select(func.count()).select_from(CreditReservation))
        ).scalar_one()
        ledger_count = (
            await session.execute(select(func.count()).select_from(CreditLedgerEntry))
        ).scalar_one()

    assert credits == Decimal("0")
    assert bonus_credits == Decimal("0")
    assert reservation_count == 1
    assert ledger_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("leader", "expected_status"),
    [
        ("settle", ReservationStatus.SETTLED),
        ("release", ReservationStatus.RELEASED),
    ],
)
async def test_concurrent_settle_and_release_share_one_terminal_outcome(
    reservation_db,
    leader: str,
    expected_status: ReservationStatus,
):
    user_id = f"{leader}-race-user"
    await _seed_user_with_balance(
        reservation_db.session_factory,
        user_id=user_id,
        credits=Decimal("1"),
    )

    reservation_repo = _BlockingReservationRepository()
    usage_service = _RecordingUsageService()
    service = _make_service(
        reservation_repo=reservation_repo,
        usage_service=usage_service,
    )
    quote = BillingQuote(
        strategy="bounded",
        reserve_usd=Decimal("0.015"),
        max_usd=Decimal("0.015"),
    )

    async with reservation_db.session_factory() as session:
        hold = await service.reserve(
            session,
            user_id=user_id,
            source_domain="chat_llm",
            source_id=f"{leader}-call",
            billing_kind="llm_usage",
            quote=quote,
            idempotency_key=f"{leader}-hold",
        )
        await session.commit()

    second_started = asyncio.Event()

    async def _settle(started: asyncio.Event | None = None):
        async with reservation_db.session_factory() as session:
            if started is not None:
                started.set()
            result = await service.settle(
                session,
                reservation_id=hold.reservation_id,
                actual_credits=Decimal("1"),
                actual_usd=Decimal("0.015"),
                usage_payload={"app_kind": "chat", "provider": "test"},
            )
            await session.commit()
            return result

    async def _release(started: asyncio.Event | None = None):
        async with reservation_db.session_factory() as session:
            if started is not None:
                started.set()
            result = await service.release(
                session,
                reservation_id=hold.reservation_id,
                reason="cancelled",
            )
            await session.commit()
            return result

    first_call = _settle if leader == "settle" else _release
    second_call = _release if leader == "settle" else _settle

    first_task = asyncio.create_task(first_call())
    await asyncio.wait_for(reservation_repo.first_lock_acquired.wait(), timeout=5)

    second_task = asyncio.create_task(second_call(second_started))
    await asyncio.wait_for(second_started.wait(), timeout=5)
    await asyncio.sleep(0.1)
    assert not second_task.done()

    reservation_repo.release_first_lock.set()
    first_result, second_result = await asyncio.wait_for(
        asyncio.gather(first_task, second_task),
        timeout=5,
    )

    assert first_result.status == expected_status
    assert second_result.status == expected_status

    async with reservation_db.session_factory() as session:
        reservation = await session.get(CreditReservation, hold.reservation_id)
        assert reservation is not None

        credits, bonus_credits = (
            await session.execute(
                select(
                    CreditBalanceRecord.credits,
                    CreditBalanceRecord.bonus_credits,
                ).where(CreditBalanceRecord.user_id == user_id)
            )
        ).one()
        ledger_count = (
            await session.execute(select(func.count()).select_from(CreditLedgerEntry))
        ).scalar_one()

    assert reservation.status == expected_status

    if expected_status == ReservationStatus.SETTLED:
        assert credits == Decimal("0")
        assert bonus_credits == Decimal("0")
        assert ledger_count == 1
        assert len(usage_service.calls) == 1
    else:
        assert credits == Decimal("1")
        assert bonus_credits == Decimal("0")
        assert ledger_count == 2
        assert usage_service.calls == []
