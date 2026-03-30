"""Billing recovery jobs for the reservation system.

These run as in-process APScheduler tasks alongside the existing stale-run
cleanup jobs.  They close the operational gap described in credit_fix.md:

- expire_stale_reservations: release holds that were never settled
- retry_shortfall_settlement_failures: replay captured shortfall settlements
- alert_settlement_failures: surface reservations stuck in settlement_failed
"""

from __future__ import annotations

from datetime import datetime, timezone

from ii_agent.billing.reservations.repository import CreditReservationRepository
from ii_agent.billing.reservations.service import CreditReservationService
from ii_agent.billing.reservations.types import ReservationStatus
from ii_agent.core.container import ServiceContainer
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.core.logger import logger


def _build_reservation_service() -> CreditReservationService:
    """Wire a standalone reservation service for the cron context."""
    return _build_container().credit_reservation_service


def _build_container() -> ServiceContainer:
    """Wire a fresh service container for cron-triggered recovery work."""
    return ServiceContainer.create()


# ---------------------------------------------------------------------------
# Job 1: expire stale reservations
# ---------------------------------------------------------------------------

_EXPIRE_BATCH_LIMIT = 200


async def expire_stale_reservations() -> None:
    """Recover reserved holds whose expires_at has passed.

    Runs every 15 minutes.  Plain stale reservations are released.  Stale
    reservations that already captured exact settlement input are replayed or
    moved to ``settlement_failed`` so they do not remain stranded in
    ``reserved`` forever after a crash between capture and settle.
    """
    try:
        svc = _build_reservation_service()
        cutoff = datetime.now(timezone.utc)

        async with get_db_session_local() as db:
            expired_count = await svc.expire_stale(db, older_than=cutoff, limit=_EXPIRE_BATCH_LIMIT)
            await db.commit()

        if expired_count:
            logger.warning(
                "Expired {} stale credit reservations older than {}",
                expired_count,
                cutoff.isoformat(),
            )
        else:
            logger.debug("No stale credit reservations to expire")

    except Exception:
        logger.opt(exception=True).error("expire_stale_reservations failed")


# ---------------------------------------------------------------------------
# Job 2: retry replayable shortfall failures
# ---------------------------------------------------------------------------

_RETRY_SHORTFALL_BATCH = 50


async def retry_shortfall_settlement_failures() -> None:
    """Replay captured shortfall failures and unblock users when fully reconciled."""
    try:
        repo = CreditReservationRepository()
        container = _build_container()
        replayed = 0
        unresolved = 0
        cleared_users = 0

        async with get_db_session_local() as db:
            failed = await repo.list_replayable_shortfall_failures_batch(
                db, limit=_RETRY_SHORTFALL_BATCH
            )
            if not failed:
                logger.debug("No replayable shortfall settlement failures to retry")
                return

            touched_users: set[str] = set()
            for reservation in failed:
                touched_users.add(reservation.user_id)
                try:
                    result = (
                        await container.credit_reservation_service.retry_settlement_from_capture(
                            db,
                            reservation_id=reservation.id,
                        )
                    )
                except Exception:
                    unresolved += 1
                    logger.opt(exception=True).error(
                        "Automatic shortfall settlement retry failed for reservation {}",
                        reservation.id,
                    )
                    continue

                status = (
                    result.status.value
                    if isinstance(result.status, ReservationStatus)
                    else str(result.status)
                )
                if status == ReservationStatus.SETTLED.value:
                    replayed += 1
                    continue

                unresolved += 1
                logger.warning(
                    "Automatic shortfall settlement retry for reservation {} remained in status {}",
                    reservation.id,
                    status,
                )

            for user_id in touched_users:
                if await repo.has_blocking_settlement_failures(db, user_id=user_id):
                    continue
                cleared = await container.credit_service.clear_billing_status(db, user_id)
                if cleared:
                    cleared_users += 1

        logger.info(
            "Shortfall settlement retry completed: replayed={} unresolved={} cleared_users={}",
            replayed,
            unresolved,
            cleared_users,
        )

    except Exception:
        logger.opt(exception=True).error("retry_shortfall_settlement_failures failed")


# ---------------------------------------------------------------------------
# Job 3: alert on settlement failures
# ---------------------------------------------------------------------------

_FAILED_SETTLEMENT_BATCH = 50


async def alert_settlement_failures() -> None:
    """Log reservations stuck in settlement_failed for operator attention.

    Runs every 5 minutes.  These represent reservations where the provider
    work was done but the final credit settlement could not complete
    (e.g. shortfall with insufficient remaining balance).  The account is
    already marked reconciliation_required so the user is blocked from
    new paid work — this job surfaces the details for ops.
    """
    try:
        repo = CreditReservationRepository()

        async with get_db_session_local() as db:
            failed = await repo.list_settlement_failed(db, limit=_FAILED_SETTLEMENT_BATCH)
            if not failed:
                return

            logger.warning("Found {} reservations in settlement_failed state", len(failed))
            for r in failed:
                logger.warning(
                    "settlement_failed: reservation={} user={} source={}:{} reserved={:.4f} error={} created={}",
                    r.id,
                    r.user_id,
                    r.source_domain,
                    r.source_id,
                    float(r.reserved_credits + r.reserved_bonus_credits),
                    r.last_error,
                    r.created_at.isoformat() if r.created_at else "?",
                )

    except Exception:
        logger.opt(exception=True).error("alert_settlement_failures failed")
