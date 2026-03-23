"""Tests for billing recovery replay jobs."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ii_agent.billing.reservations.types import ReservationStatus
from ii_agent.workers.cron import billing_recovery


class _FakeReservationRepo:
    def __init__(self, *, batch, remaining_by_user=None, blocking_by_user=None):
        self.batch = batch
        self.remaining_by_user = remaining_by_user or {}
        self.blocking_by_user = blocking_by_user or {}

    async def list_replayable_shortfall_failures_batch(self, db, *, limit=50):
        return self.batch[:limit]

    async def has_replayable_shortfall_failures(self, db, *, user_id):
        return self.remaining_by_user.get(user_id, False)

    async def has_blocking_settlement_failures(self, db, *, user_id):
        return self.blocking_by_user.get(user_id, False)


@asynccontextmanager
async def _fake_db_session():
    yield None


@pytest.mark.asyncio
async def test_retry_shortfall_failures_clears_billing_status_when_user_is_fully_replayed(
    monkeypatch,
):
    repo = _FakeReservationRepo(
        batch=[SimpleNamespace(id="res-1", user_id="user-1")],
        remaining_by_user={"user-1": False},
    )
    container = SimpleNamespace(
        credit_reservation_service=SimpleNamespace(
            retry_settlement_from_capture=AsyncMock(
                return_value=SimpleNamespace(status=ReservationStatus.SETTLED)
            )
        ),
        credit_service=SimpleNamespace(clear_billing_status=AsyncMock(return_value=True)),
    )

    monkeypatch.setattr(billing_recovery, "CreditReservationRepository", lambda: repo)
    monkeypatch.setattr(billing_recovery, "_build_container", lambda: container)
    monkeypatch.setattr(billing_recovery, "get_db_session_local", _fake_db_session)

    await billing_recovery.retry_shortfall_settlement_failures()

    container.credit_reservation_service.retry_settlement_from_capture.assert_awaited_once_with(
        None,
        reservation_id="res-1",
    )
    container.credit_service.clear_billing_status.assert_awaited_once_with(None, "user-1")


@pytest.mark.asyncio
async def test_retry_shortfall_failures_keeps_block_when_more_replays_remain(monkeypatch):
    repo = _FakeReservationRepo(
        batch=[SimpleNamespace(id="res-2", user_id="user-2")],
        remaining_by_user={"user-2": True},
        blocking_by_user={"user-2": True},
    )
    container = SimpleNamespace(
        credit_reservation_service=SimpleNamespace(
            retry_settlement_from_capture=AsyncMock(
                return_value=SimpleNamespace(status=ReservationStatus.SETTLED)
            )
        ),
        credit_service=SimpleNamespace(clear_billing_status=AsyncMock(return_value=True)),
    )

    monkeypatch.setattr(billing_recovery, "CreditReservationRepository", lambda: repo)
    monkeypatch.setattr(billing_recovery, "_build_container", lambda: container)
    monkeypatch.setattr(billing_recovery, "get_db_session_local", _fake_db_session)

    await billing_recovery.retry_shortfall_settlement_failures()

    container.credit_reservation_service.retry_settlement_from_capture.assert_awaited_once_with(
        None,
        reservation_id="res-2",
    )
    container.credit_service.clear_billing_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_shortfall_failures_keeps_block_when_generic_failures_remain(monkeypatch):
    repo = _FakeReservationRepo(
        batch=[SimpleNamespace(id="res-3", user_id="user-3")],
        remaining_by_user={"user-3": False},
        blocking_by_user={"user-3": True},
    )
    container = SimpleNamespace(
        credit_reservation_service=SimpleNamespace(
            retry_settlement_from_capture=AsyncMock(
                return_value=SimpleNamespace(status=ReservationStatus.SETTLED)
            )
        ),
        credit_service=SimpleNamespace(clear_billing_status=AsyncMock(return_value=True)),
    )

    monkeypatch.setattr(billing_recovery, "CreditReservationRepository", lambda: repo)
    monkeypatch.setattr(billing_recovery, "_build_container", lambda: container)
    monkeypatch.setattr(billing_recovery, "get_db_session_local", _fake_db_session)

    await billing_recovery.retry_shortfall_settlement_failures()

    container.credit_reservation_service.retry_settlement_from_capture.assert_awaited_once_with(
        None,
        reservation_id="res-3",
    )
    container.credit_service.clear_billing_status.assert_not_awaited()
