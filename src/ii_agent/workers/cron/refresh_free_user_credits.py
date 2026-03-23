"""Monthly cron helper to refresh credits for free-plan users."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import select

from ii_agent.core.config.settings import get_settings
from ii_agent.core.logger import logger as app_logger
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.auth.users.models import User
from ii_agent.billing.credits.ledger_models import LedgerEntryType
from ii_agent.billing.reservations.types import SourceDomain
from ii_agent.workers.cron.cron_manager import CronJobDefinition, CronManager

FREE_PLAN_ID = "free"
DEFAULT_CRON_SCHEDULE = "0 0 1 * *"


def _monthly_free_credit_allowance() -> float:
    """Return the configured monthly credit allowance for free users."""

    settings = get_settings()
    allowance = settings.credits.default_plans_credits.get(FREE_PLAN_ID)
    if allowance is None:
        allowance = settings.credits.default_user_credits
        app_logger.warning(
            "No configured credit allowance for free plan; falling back to default_user_credits={}",
            allowance,
        )
    return allowance


async def refresh_free_user_credits() -> None:
    """Reset credits for free users to the configured monthly allowance."""

    monthly_credits = _monthly_free_credit_allowance()
    updated_users = 0

    from ii_agent.billing.customers.repository import BillingCustomerRepository
    from ii_agent.billing.customers.service import BillingCustomerService
    from ii_agent.billing.credits.balance_repository import CreditBalanceRepository
    from ii_agent.billing.credits.service import CreditService

    billing_customer_service = BillingCustomerService(customer_repo=BillingCustomerRepository())
    balance_repo = CreditBalanceRepository()
    credit_service = CreditService(balance_repo=balance_repo)

    async with get_db_session_local() as db:
        result = await db.execute(select(User).where(User.is_active.is_(True)))
        users = result.scalars().all()
        customers_by_user = await billing_customer_service.list_by_user_ids(
            db,
            [user.id for user in users],
            provider="stripe",
        )

        for user in users:
            customer = customers_by_user.get(user.id)
            billing_profile = billing_customer_service.resolve_effective_profile(
                customer=customer,
            )
            if billing_profile.subscription_plan not in {None, FREE_PLAN_ID}:
                continue

            changed = False
            if customer and customer.subscription_plan != FREE_PLAN_ID:
                await billing_customer_service.update_subscription(
                    db,
                    user.id,
                    provider="stripe",
                    subscription_plan=FREE_PLAN_ID,
                )
                changed = True

            try:
                result = await credit_service.reset_plan_balance(
                    db,
                    user.id,
                    monthly_credits,
                    entry_type=LedgerEntryType.REFRESH,
                    source_domain=SourceDomain.CRON,
                    entry_metadata={"plan": FREE_PLAN_ID},
                )
                if result.updated:
                    changed = True
            except Exception:
                app_logger.opt(exception=True).warning("Failed to set balance for user {}", user.id)
                continue

            if changed:
                updated_users += 1

        await db.flush()

    app_logger.info("Free user credit refresh completed: {} users updated", updated_users)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _default_command() -> str:
    python_executable = sys.executable
    repo_root = _project_root()
    return (
        f"cd {repo_root} && {python_executable} -m ii_agent.workers.cron.refresh_free_user_credits"
    )


def install_cron_job(
    *,
    schedule: str = DEFAULT_CRON_SCHEDULE,
    dry_run: bool = False,
    manager: CronManager | None = None,
) -> None:
    """Install or update the cron job that runs the free-plan refresh task."""

    cron_manager = manager or CronManager()
    job = build_cron_job_definition(schedule=schedule)
    cron_manager.install(job=job, dry_run=dry_run)


def build_cron_job_definition(
    *,
    schedule: str = DEFAULT_CRON_SCHEDULE,
) -> CronJobDefinition:
    """Return the cron job definition for the free-plan credit refresh."""

    return CronJobDefinition(
        name="ii-agent-free-credit-refresh",
        schedule=schedule,
        command=_default_command(),
    )


async def _main_async() -> None:
    await refresh_free_user_credits()


def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Refresh credits for free-plan users or install the cron job"
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
