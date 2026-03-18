"""Application lifespan wiring."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ii_agent.settings.skills.seeding import ensure_builtin_skills_synced
from ii_agent.core.config.settings import get_settings
from ii_agent.core.container import ServiceContainer
from ii_agent.core.redis import close_redis
from ii_agent.settings.llm.seeding import ensure_admin_llm_settings_seeded
from ii_agent.workers.cron.tasks import shutdown_scheduler, start_scheduler

logger = logging.getLogger(__name__)


def create_lifespan():
    """Create the FastAPI lifespan context manager."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        container = ServiceContainer.create()
        app.state.container = container

        if hasattr(app.state, "sio_manager"):
            sio_manager = app.state.sio_manager
            sio_manager.set_container(container)
            await sio_manager.init()
            logger.info("Socket.IO manager initialized during startup")

        settings = get_settings()
        app.state.settings = settings

        if os.getenv("II_AGENT_SKIP_MIGRATIONS", "").lower() not in ("1", "true", "yes"):
            from ii_agent.core.db.manager import run_migrations

            run_migrations()
            logger.info("Database migrations applied")
        else:
            logger.info("Skipping database migrations (II_AGENT_SKIP_MIGRATIONS)")

        try:
            await ensure_admin_llm_settings_seeded()
            await ensure_builtin_skills_synced()
        except Exception as exc:
            logger.error("Failed to initialize startup seeds: %s", exc)

        start_scheduler()

        yield

        if hasattr(app.state, "sio_manager"):
            await app.state.sio_manager.shutdown()
            logger.info("Socket.IO manager shut down")
        await close_redis()
        shutdown_scheduler()

    return lifespan
