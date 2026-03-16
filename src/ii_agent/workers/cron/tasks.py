"""
Scheduled tasks for cleaning up stale agent run tasks.
"""

from datetime import datetime, timedelta, timezone
import uuid
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.agent.events.repository import EventRepository
from ii_agent.core.db.manager import get_db
from ii_agent.agent.runs.models import AgentRunTask, RunStatus
from ii_agent.chat.runs.models import ChatRun, ChatRunStatus
from ii_agent.core.logger import logger


# Initialize the scheduler
scheduler = AsyncIOScheduler()


async def cleanup_long_running_tasks():
    """
    Clean up AgentRunTasks that have been running for more than 45 minutes.
    Marks them as system_interrupted instead of deleting.
    """
    try:
        # Calculate the cutoff time (45 minutes ago)
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=45)
        total_processed = 0
        batch_size = 20
        max_processed = 100

        logger.info(f"Starting cleanup of AgentRunTasks older than {cutoff_time}")

        async with get_db() as db:
            while total_processed < max_processed:
                # Select tasks older than 45 minutes with FOR UPDATE SKIP LOCKED
                # This ensures we don't block on locked rows and prevents concurrent updates
                # Only select tasks that are currently in RUNNING status
                stmt = (
                    select(AgentRunTask)
                    .where(
                        AgentRunTask.created_at < cutoff_time,
                        AgentRunTask.status == RunStatus.RUNNING,
                    )
                    .order_by(AgentRunTask.created_at.desc())
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )

                result = await db.execute(stmt)
                tasks = result.scalars().all()

                if not tasks:
                    logger.info("No more stale AgentRunTasks found")
                    break

                # Update each task - optimistic locking will be enforced on commit
                batch_count = len(tasks)

                event_repo = EventRepository()
                for task in tasks:
                    # Update the task status - this will use optimistic locking via version column
                    task.status = RunStatus.SYSTEM_INTERRUPTED
                    task.updated_at = datetime.now(timezone.utc)
                    # The version column will be automatically incremented by SQLAlchemy on commit
                    event = RealtimeEvent(
                        session_id=uuid.UUID(task.session_id),
                        run_id=task.id,
                        type=EventType.AGENT_RESPONSE_INTERRUPTED,
                        content={
                            "message": "Agent run task was interrupted by system cleanup due to timeout."
                        },
                    )
                    await event_repo.save(db, uuid.UUID(task.session_id), event)
                # Commit all updates in one transaction
                await db.commit()

                total_processed += batch_count
                logger.info(
                    f"Marked {batch_count} stale AgentRunTasks as system_interrupted. "
                    f"Total processed: {total_processed}/{max_processed}"
                )

                if batch_count < batch_size:
                    break

                if total_processed >= max_processed:
                    logger.info(
                        f"Reached max processed limit ({max_processed}). "
                        "Remaining tasks will be processed in next run."
                    )
                    break

        logger.info(
            f"Cleanup completed. Total AgentRunTasks marked as system_interrupted: {total_processed}"
        )

    except Exception as e:
        logger.error(f"Error during AgentRunTask cleanup: {e}", exc_info=True)
        # Don't re-raise - we want the scheduler to continue running


async def cleanup_long_running_chat_runs():
    """
    Clean up ChatRuns that have been running for more than 45 minutes.
    Marks them as aborted.
    """
    try:
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=45)
        total_processed = 0
        batch_size = 20
        max_processed = 100

        logger.info(f"Starting cleanup of ChatRuns older than {cutoff_time}")

        async with get_db() as db:
            while total_processed < max_processed:
                stmt = (
                    select(ChatRun)
                    .where(
                        ChatRun.created_at < cutoff_time,
                        ChatRun.status == ChatRunStatus.RUNNING,
                    )
                    .order_by(ChatRun.created_at.desc())
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )

                result = await db.execute(stmt)
                runs = result.scalars().all()

                if not runs:
                    logger.info("No more stale ChatRuns found")
                    break

                batch_count = len(runs)

                for run in runs:
                    run.status = ChatRunStatus.ABORTED
                    run.updated_at = datetime.now(timezone.utc)

                await db.commit()

                total_processed += batch_count
                logger.info(
                    f"Marked {batch_count} stale ChatRuns as aborted. "
                    f"Total processed: {total_processed}/{max_processed}"
                )

                if batch_count < batch_size:
                    break

                if total_processed >= max_processed:
                    logger.info(
                        f"Reached max processed limit ({max_processed}). "
                        "Remaining chat runs will be processed in next run."
                    )
                    break

        logger.info(
            f"Chat run cleanup completed. Total ChatRuns marked as aborted: {total_processed}"
        )

    except Exception as e:
        logger.error(f"Error during ChatRun cleanup: {e}", exc_info=True)


def start_scheduler():
    """
    Start the scheduler and add all periodic jobs.
    """
    try:
        from ii_agent.workers.cron.billing_recovery import (
            alert_settlement_failures,
            expire_stale_reservations,
            retry_billing_usage_facts,
        )

        # ── Run / chat cleanup ────────────────────────────────────────────
        scheduler.add_job(
            cleanup_long_running_tasks,
            trigger=IntervalTrigger(minutes=40),
            id="cleanup_stale_agent_run_tasks",
            name="Cleanup stale AgentRunTasks (older than 45 mins)",
            replace_existing=True,
            max_instances=1,
        )

        scheduler.add_job(
            cleanup_long_running_chat_runs,
            trigger=IntervalTrigger(minutes=40),
            id="cleanup_stale_chat_runs",
            name="Cleanup stale ChatRuns (older than 45 mins)",
            replace_existing=True,
            max_instances=1,
        )

        # ── Billing recovery ──────────────────────────────────────────────
        scheduler.add_job(
            expire_stale_reservations,
            trigger=IntervalTrigger(minutes=15),
            id="expire_stale_reservations",
            name="Release stale credit reservation holds",
            replace_existing=True,
            max_instances=1,
        )

        scheduler.add_job(
            retry_billing_usage_facts,
            trigger=IntervalTrigger(minutes=1),
            id="retry_billing_usage_facts",
            name="Retry captured billing usage facts",
            replace_existing=True,
            max_instances=1,
        )

        scheduler.add_job(
            alert_settlement_failures,
            trigger=IntervalTrigger(minutes=5),
            id="alert_settlement_failures",
            name="Log reservations stuck in settlement_failed",
            replace_existing=True,
            max_instances=1,
        )

        # Start the scheduler
        scheduler.start()
        logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    except Exception as e:
        logger.error(f"Error starting scheduler: {e}", exc_info=True)
        raise


def shutdown_scheduler():
    """
    Shutdown the scheduler gracefully.
    """
    try:
        if scheduler.running:
            scheduler.shutdown(wait=True)
            logger.info("Scheduler shutdown successfully")
    except Exception as e:
        logger.error(f"Error shutting down scheduler: {e}", exc_info=True)
