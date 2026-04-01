"""Scheduled jobs — periodic task management.

Consolidates cron/scheduled job functionality from ``ii_agent.cron``
into the workers package. Provides APScheduler-based scheduling for:

- Stale agent run cleanup (every 40 minutes)
- Sandbox timeout extension for permanent sessions

Re-exports from the original ``ii_agent.cron.tasks`` module during
the migration period.
"""

from __future__ import annotations

from ii_agent.cron.tasks import (  # noqa: F401
    cleanup_long_running_tasks,
    scheduler,
    shutdown_scheduler,
    start_scheduler,
)
from ii_agent.core.logger import logger


def start_all_scheduled_jobs() -> None:
    """Start all scheduled background jobs.

    This is the single entry-point for initialising periodic tasks
    at application startup.
    """
    start_scheduler()
    logger.info("All scheduled jobs started via workers.cron")


def shutdown_all_scheduled_jobs() -> None:
    """Gracefully shut down all scheduled jobs."""
    shutdown_scheduler()
    logger.info("All scheduled jobs shut down via workers.cron")


__all__ = [
    "cleanup_long_running_tasks",
    "scheduler",
    "start_scheduler",
    "shutdown_scheduler",
    "start_all_scheduled_jobs",
    "shutdown_all_scheduled_jobs",
]
