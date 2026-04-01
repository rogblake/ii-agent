"""Daily cron helper to refresh monthly credits for annual subscribers.

This module can either run the refresh immediately or install a cron job
using ``python-crontab`` to execute the task on a schedule.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from ii_agent.core.config.settings import get_settings
from ii_agent.core.logger import logger as app_logger
from ii_agent.core.db import get_db_session_local
from ii_agent.users.models import User
from ii_agent.workers.cron.cron_manager import CronJobDefinition, CronManager

REFRESH_METADATA_KEY = "last_annual_credit_refresh"
ACTIVE_STATUSES = {"active", "trialing"}
DEFAULT_CRON_SCHEDULE = "0 0 * * *"


def _ensure_metadata_dict(metadata: Any | None) -> Dict[str, Any]:
    if isinstance(metadata, dict):
        return dict(metadata)
    return {}


def _parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _should_refresh(
    user: User,
    *,
    now: datetime,
    plan_id: str | None,
    period_end: datetime | None = None,
) -> tuple[bool, float | None]:
    """Check if user needs a credit refresh. Returns (should_refresh, monthly_credits)."""
    monthly_credits = get_settings().credits.default_plans_credits.get(plan_id or "")
    if monthly_credits is None:
        app_logger.warning(
            "Skipping annual credit refresh for user {}: plan '{}' has no default credits",
            user.id,
            plan_id,
        )
        return False, None

    subscription_period_end = _as_utc(period_end)
    if subscription_period_end and subscription_period_end < now:
        return False, None

    metadata = _ensure_metadata_dict(user.user_metadata)
    last_refresh = _parse_iso_date(str(metadata.get(REFRESH_METADATA_KEY)))
    if last_refresh and last_refresh.year == now.year and last_refresh.month == now.month:
        return False, None

    return True, monthly_credits


async def refresh_annual_subscription_credits() -> None:
    now = datetime.now(timezone.utc)
    refreshed = 0

    # BillingCustomerService was removed during refactoring.
    # This cron job needs migration to use the new billing/credits modules.
    app_logger.warning(
        "refresh_annual_subscription_credits skipped: "
        "BillingCustomerService not yet migrated"
    )
    return

    async with get_db_session_local() as db:  # noqa: E501  # unreachable until migrated
        # Subscription state now lives in billing_customers.
        bc_rows = await billing_customer_service.list_by_subscription(
            db,
            provider="stripe",
            subscription_statuses=ACTIVE_STATUSES,
            subscription_billing_cycle="annually",
        )

        for bc in bc_rows:
            # Load the user for metadata (last refresh tracking)
            user = await db.get(User, bc.user_id)
            if not user or not user.is_active:
                continue

            should, monthly_credits = _should_refresh(
                user,
                now=now,
                plan_id=bc.subscription_plan,
                period_end=bc.subscription_current_period_end,
            )
            if not should or monthly_credits is None:
                continue

            try:
                await credit_service.set_subscription_credits(
                    db,
                    user_id=user.id,
                    plan_credits=monthly_credits,
                    plan_id=bc.subscription_plan,
                    metadata={"cycle": "annually"},
                )
            except Exception:
                app_logger.opt(exception=True).warning(
                    "Failed to set balance for user {}",
                    user.id,
                )
                continue

            metadata = _ensure_metadata_dict(user.user_metadata)
            metadata[REFRESH_METADATA_KEY] = now.isoformat()
            user.user_metadata = metadata
            refreshed += 1

        await db.flush()

    app_logger.info("Annual subscription credit refresh completed: {} users updated", refreshed)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _default_command() -> str:
    python_executable = sys.executable
    repo_root = _project_root()
    return (
        f"cd {repo_root} && {python_executable} -m "
        "ii_agent.workers.cron.refresh_annual_subscription_credits"
    )


def install_cron_job(
    *,
    schedule: str,
    dry_run: bool = False,
    manager: CronManager | None = None,
) -> None:
    """Install or update the cron job that runs the refresh task."""

    cron_manager = manager or CronManager()
    job = build_cron_job_definition(
        schedule=schedule,
    )
    cron_manager.install(job=job, dry_run=dry_run)


def build_cron_job_definition(
    *,
    schedule: str = DEFAULT_CRON_SCHEDULE,
) -> CronJobDefinition:
    """Return the cron job definition for annual credit refresh."""

    return CronJobDefinition(
        name="ii-agent-annual-credit-refresh",
        schedule=schedule,
        command=_default_command(),
    )


async def _main_async() -> None:
    await refresh_annual_subscription_credits()


def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Refresh credits for annual subscribers or install cron job"
    )
    parser.add_argument(
        "--install-cron",
        action="store_true",
        help="Install the cron job instead of running the refresh now",
    )
    parser.add_argument(
        "--schedule",
        default=DEFAULT_CRON_SCHEDULE,
        help=f"Cron schedule in crontab format (default: '{DEFAULT_CRON_SCHEDULE}')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the cron job that would be installed without writing it",
    )

    args = parser.parse_args()

    if args.install_cron:
        install_cron_job(
            schedule=args.schedule,
            dry_run=args.dry_run,
        )
    else:
        asyncio.run(_main_async())


if __name__ == "__main__":
    main()
