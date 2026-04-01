"""Celery application configuration.

This module sets up the Celery application with Redis as the broker and backend.
Migrated from ``ii_agent.celery.app`` as part of the ADR-003 restructuring.

IMPORTANT: Database migrations must be disabled for Celery workers.
Set II_AGENT_SKIP_MIGRATIONS=1 via:
  - Docker Compose environment (for containerized workers)
  - CLI environment variable (for local development)

Do NOT set this env var in Python code, as it would affect any process
that imports this module (including the main API server).
"""

# Initialize logging FIRST before any other imports
# This ensures our loguru configuration runs before third-party packages
import ii_agent.core.logger  # noqa: F401, E402

import os

from celery import Celery
from celery.signals import setup_logging, worker_process_init
from kombu import Exchange, Queue

from ii_agent.core.config.settings import get_settings
from ii_agent.core.logger import reconfigure_logging


@setup_logging.connect
def on_setup_logging(**kwargs):
    """Prevent Celery from overriding our logging setup."""
    reconfigure_logging()


@worker_process_init.connect
def on_worker_process_init(**kwargs):
    """Re-apply dictConfig after all task modules are imported.

    Libraries like ii_agent_tools may add their own StreamHandlers
    during import; this cleans them up so only loguru handles output.
    """
    reconfigure_logging()


def get_celery_broker_url() -> str:
    """Get Redis broker URL for Celery."""
    # Use a separate Redis database for Celery (db 2) to avoid conflicts
    # with session storage (db 1) and other uses (db 0)
    celery_broker_url = os.environ.get("CELERY_BROKER_URL")
    if celery_broker_url:
        return celery_broker_url

    # Derive from Redis session URL if available
    redis_url = get_settings().redis.session_url
    if redis_url:
        # Replace database number with 2 for Celery
        if redis_url.endswith("/0") or redis_url.endswith("/1"):
            return redis_url[:-1] + "2"
        return redis_url + "/2" if not redis_url.endswith("/") else redis_url + "2"

    return "redis://localhost:6379/2"


def get_celery_result_backend() -> str:
    """Get Redis result backend URL for Celery."""
    celery_result_backend = os.environ.get("CELERY_RESULT_BACKEND")
    if celery_result_backend:
        return celery_result_backend

    # Use the same URL as broker for simplicity
    return get_celery_broker_url()


# Create the Celery application
celery_app = Celery(
    "ii_agent",
    broker=get_celery_broker_url(),
    backend=get_celery_result_backend(),
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Result settings
    result_expires=3600,  # Results expire after 1 hour
    result_extended=True,  # Store additional task metadata
    # Task execution settings
    task_acks_late=True,  # Acknowledge task after completion (for reliability)
    task_reject_on_worker_lost=True,  # Reject task if worker dies
    task_time_limit=3600,  # Hard time limit: 1 hour
    task_soft_time_limit=3300,  # Soft time limit: 55 minutes (allows graceful shutdown)
    # Worker settings
    worker_prefetch_multiplier=1,  # Fetch one task at a time (for long-running tasks)
    worker_concurrency=4,  # Number of concurrent workers
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks (memory leak prevention)
    # Broker settings
    broker_connection_retry_on_startup=True,
    broker_pool_limit=10,
    # Task routing
    task_default_queue="default",
    task_queues=(
        Queue("default", Exchange("default"), routing_key="default"),
        Queue("high_priority", Exchange("high_priority"), routing_key="high_priority"),
        Queue("low_priority", Exchange("low_priority"), routing_key="low_priority"),
    ),
    # Task routes - define which tasks go to which queues
    task_routes={
        "ii_agent.workers.tasks.*": {"queue": "default"},
        # Keep backward compat with old task names during migration
        "ii_agent.celery.tasks.*": {"queue": "default"},
    },
    # Beat schedule (for periodic tasks) - empty by default
    beat_schedule={},
)

# Auto-discover tasks from the tasks module
celery_app.autodiscover_tasks(["ii_agent.workers", "ii_agent.celery"])
