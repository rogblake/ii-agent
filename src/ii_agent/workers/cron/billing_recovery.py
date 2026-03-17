"""Billing recovery jobs for the reservation system.

These run as in-process APScheduler tasks alongside the existing stale-run
cleanup jobs.  They close the operational gap described in credit_fix.md:

- expire_stale_reservations: release holds that were never settled
- retry_billing_usage_facts: replay durable invocation facts after settle failures
- alert_settlement_failures: surface reservations stuck in settlement_failed
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ii_agent.billing.reservations.repository import CreditReservationRepository
from ii_agent.billing.reservations.service import CreditReservationService
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
    """Release reserved holds whose expires_at has passed.

    Runs every 15 minutes.  A reservation that was never settled or released
    (e.g. worker crash, network failure) will have credits locked forever
    without this job.
    """
    try:
        svc = _build_reservation_service()
        cutoff = datetime.now(timezone.utc)

        async with get_db_session_local() as db:
            expired_count = await svc.expire_stale(
                db, older_than=cutoff, limit=_EXPIRE_BATCH_LIMIT
            )
            await db.commit()

        if expired_count:
            logger.warning(
                "Expired %d stale credit reservations older than %s",
                expired_count,
                cutoff.isoformat(),
            )
        else:
            logger.debug("No stale credit reservations to expire")

    except Exception:
        logger.error("expire_stale_reservations failed", exc_info=True)


# ---------------------------------------------------------------------------
# Job 2: retry billing facts
# ---------------------------------------------------------------------------

_RETRY_FACT_BATCH_LIMIT = 50


async def retry_billing_usage_facts() -> None:
    """Retry durable billing facts that were captured but not fully processed."""
    try:
        llm_billing = _build_container().llm_billing_service

        async with get_db_session_local() as db:
            retried = await llm_billing.retry_captured_usage_facts(
                db,
                limit=_RETRY_FACT_BATCH_LIMIT,
            )
            await db.commit()

        if retried:
            logger.warning("Retried %d billing usage fact(s)", retried)
        else:
            logger.debug("No captured billing usage facts to retry")

    except Exception:
        logger.error("retry_billing_usage_facts failed", exc_info=True)


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
            failed = await repo.list_settlement_failed(
                db, limit=_FAILED_SETTLEMENT_BATCH
            )
            if not failed:
                return

            logger.warning(
                "Found %d reservations in settlement_failed state",
                len(failed),
            )
            for r in failed:
                logger.warning(
                    "settlement_failed: reservation=%s user=%s source=%s:%s "
                    "reserved=%.4f error=%s created=%s",
                    r.id,
                    r.user_id,
                    r.source_domain,
                    r.source_id,
                    float(r.reserved_credits + r.reserved_bonus_credits),
                    r.last_error,
                    r.created_at.isoformat() if r.created_at else "?",
                )

    except Exception:
        logger.error("alert_settlement_failures failed", exc_info=True)
