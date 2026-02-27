"""
Celery application configuration.

This module sets up the Celery application with Redis as the broker and backend.

IMPORTANT: Database migrations must be disabled for Celery workers.
Set II_AGENT_SKIP_MIGRATIONS=1 via:
  - Docker Compose environment (for containerized workers)
  - CLI environment variable (for local development)

Do NOT set this env var in Python code, as it would affect any process
that imports this module (including the main API server).
"""

# Initialize logging FIRST before any other imports
import ii_agent.core.logger  # noqa: F401, E402

import os
import platform

from celery import Celery
from celery.signals import setup_logging, worker_process_init
from kombu import Exchange, Queue

from ii_agent.workers.celery.model_imports import import_model_modules
from ii_agent.core.config.settings import get_settings
from ii_agent.core.logger import reconfigure_logging

# Import ORM modules up-front so Celery workers don't depend on incidental imports.
import_model_modules()


@setup_logging.connect
def on_setup_logging(**kwargs):
    """Prevent Celery from overriding our logging setup."""
    reconfigure_logging()


@worker_process_init.connect
def on_worker_process_init(**kwargs):
    """Re-apply dictConfig after all task modules are imported."""
    reconfigure_logging()


def get_celery_broker_url() -> str:
    """Get Redis broker URL for Celery."""
    celery_broker_url = os.environ.get("CELERY_BROKER_URL")
    if celery_broker_url:
        return celery_broker_url

    settings = get_settings()
    redis_url = settings.redis.session_url if settings.redis else ""
    if redis_url:
        if redis_url.endswith("/0") or redis_url.endswith("/1"):
            return redis_url[:-1] + "2"
        return redis_url + "/2" if not redis_url.endswith("/") else redis_url + "2"

    return "redis://localhost:6379/2"


def get_celery_result_backend() -> str:
    """Get Redis result backend URL for Celery."""
    celery_result_backend = os.environ.get("CELERY_RESULT_BACKEND")
    if celery_result_backend:
        return celery_result_backend

    return get_celery_broker_url()


def get_celery_worker_pool() -> str:
    """Get Celery worker pool implementation.

    Defaults to ``solo`` on macOS to avoid prefork crashes with native SDKs.
    Use CELERY_WORKER_POOL to override explicitly in any environment.
    """
    configured_pool = os.environ.get("CELERY_WORKER_POOL")
    if configured_pool:
        return configured_pool
    if platform.system() == "Darwin":
        return "solo"
    return "prefork"


def get_celery_worker_concurrency(worker_pool: str) -> int:
    """Get worker concurrency with pool-aware defaults."""
    configured = os.environ.get("CELERY_WORKER_CONCURRENCY")
    if configured:
        return int(configured)
    if worker_pool == "solo":
        return 1
    return 4


celery_app = Celery(
    "ii_agent",
    broker=get_celery_broker_url(),
    backend=get_celery_result_backend(),
)

worker_pool = get_celery_worker_pool()

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    result_expires=3600,
    result_extended=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=3600,
    task_soft_time_limit=3300,
    worker_pool=worker_pool,
    worker_prefetch_multiplier=1,
    worker_concurrency=get_celery_worker_concurrency(worker_pool),
    worker_max_tasks_per_child=100,
    broker_connection_retry_on_startup=True,
    broker_pool_limit=10,
    task_default_queue="default",
    task_queues=(
        Queue("default", Exchange("default"), routing_key="default"),
        Queue("high_priority", Exchange("high_priority"), routing_key="high_priority"),
        Queue("low_priority", Exchange("low_priority"), routing_key="low_priority"),
    ),
    task_routes={
        "ii_agent.workers.celery.tasks.*": {"queue": "default"},
    },
    beat_schedule={},
)

celery_app.autodiscover_tasks(["ii_agent.workers.celery"])
