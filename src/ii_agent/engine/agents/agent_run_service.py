"""Service layer for agent run tasks - business logic only."""

import logging
import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.engine.agents.repository import AgentRunTaskRepository
from ii_agent.engine.agents.models import AgentRunTask, RunStatus
from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.core.redis import entity_cache

logger = logging.getLogger(__name__)


KEY_PATTERN = "agent_task:{task_id}"


class AgentRunTaskResponse(BaseModel):
    """Pydantic model for AgentRunTask serialization."""

    id: UUID
    session_id: str
    version: int = Field(default=0)
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        """Pydantic configuration."""

        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
        }


class AgentRunService:
    """Service for managing agent run tasks with complex business logic."""

    def __init__(self, *, repo: AgentRunTaskRepository, config: Settings) -> None:
        self._config = config
        self._repo = repo

    async def get_last_or_create_new_run(
        self, db: AsyncSession, *, session_id: uuid.UUID
    ) -> AgentRunTask:
        current_task = await self._repo.find_last_by_session_id(db, session_id)
        if current_task is None:
            current_task = await self._repo.create(
                db, session_id=session_id, status=RunStatus.RUNNING
            )
        return current_task

    async def get_task_by_id(
        self, db: AsyncSession, *, task_id: uuid.UUID
    ) -> Optional[AgentRunTaskResponse]:
        """Get an agent run task by its ID, with caching."""
        _cached_key = KEY_PATTERN.format(task_id=str(task_id))

        entity = await entity_cache.get(_cached_key)
        if entity:
            return AgentRunTaskResponse(**entity)

        task_run = await self._repo.get_by_id(db, task_id)
        if task_run is None:
            return None

        res = AgentRunTaskResponse(
            id=task_run.id,
            session_id=task_run.session_id,
            version=task_run.version,
            status=task_run.status,
            created_at=task_run.created_at,
            updated_at=task_run.updated_at,
        )

        await entity_cache.set(_cached_key, res.model_dump_json())
        return res

    async def update_task_status(
        self, db: AsyncSession, *, task_id: uuid.UUID, status: str
    ) -> AgentRunTaskResponse | None:
        """Update the status of an agent run task and evict cache."""
        task = await self._repo.update_status(db, task_id, status)
        if not task:
            return None

        _cached_key = KEY_PATTERN.format(task_id=str(task.id))
        await entity_cache.evict(_cached_key)

        return AgentRunTaskResponse(
            id=task.id,
            session_id=task.session_id,
            version=task.version,
            status=task.status,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    async def get_running_task(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> AgentRunTask | None:
        return await self._repo.find_last_by_session_id_and_status(
            db, session_id, RunStatus.RUNNING
        )

    async def get_last_by_session_id(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> AgentRunTask | None:
        return await self._repo.find_last_by_session_id(db, session_id)

    async def create_task(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        user_message_id: uuid.UUID | None = None,
        status: RunStatus = RunStatus.RUNNING,
    ) -> AgentRunTask:
        return await self._repo.create(
            db, session_id=session_id, user_message_id=user_message_id, status=status
        )

    async def get_all_running_session_ids(
        self, db: AsyncSession
    ) -> list[str]:
        """Get session IDs that have active running tasks."""
        return await self._repo.get_all_running_session_ids(db)

    async def get_running_by_session(
        self, db: AsyncSession, session_id: str
    ) -> AgentRunTask | None:
        """Get the running task for a specific session."""
        return await self._repo.get_running_by_session(db, session_id)

    async def find_running_task_for_cancel(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> AgentRunTask | None:
        """Find a running task for a session (used for cancellation)."""
        return await self._repo.find_last_by_session_id_and_status(
            db, session_id, RunStatus.RUNNING
        )

    async def get_tasks_by_session(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> list[AgentRunTask]:
        """Get all tasks for a session, most recent first."""
        return await self._repo.get_by_session_id(db, session_id)
