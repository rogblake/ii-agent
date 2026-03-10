"""Repository layer for agent run tasks - data access only."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.agent.agents.models import AgentRunTask, RunStatus


class AgentRunTaskRepository:
    """Data access layer for AgentRunTask model."""

    async def create(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        user_message_id: uuid.UUID | None = None,
        status: RunStatus = RunStatus.RUNNING,
    ) -> AgentRunTask:
        """Create a new agent run task."""
        agent_run = AgentRunTask(
            session_id=str(session_id),
            status=status,
            user_message_id=user_message_id,
        )
        db.add(agent_run)
        await db.flush()
        await db.refresh(agent_run)
        return agent_run

    async def get_by_id(self, db: AsyncSession, task_id: uuid.UUID) -> AgentRunTask | None:
        """Get an agent run task by its ID."""
        result = await db.execute(
            select(AgentRunTask).where(AgentRunTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def get_by_session_id(self, db: AsyncSession, session_id: uuid.UUID) -> list[AgentRunTask]:
        """Get all agent run tasks for a session, most recent first."""
        result = await db.execute(
            select(AgentRunTask)
            .where(AgentRunTask.session_id == str(session_id))
            .order_by(AgentRunTask.created_at.desc())
        )
        return list(result.scalars().all())

    async def find_last_by_session_id(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> AgentRunTask | None:
        """Find the most recent agent run task for a session."""
        result = await db.execute(
            select(AgentRunTask)
            .where(AgentRunTask.session_id == str(session_id))
            .order_by(AgentRunTask.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_last_by_session_id_and_status(
        self, db: AsyncSession, session_id: uuid.UUID, status: str
    ) -> AgentRunTask | None:
        """Find the most recent agent run task for a session with a given status."""
        result = await db.execute(
            select(AgentRunTask)
            .where(AgentRunTask.session_id == str(session_id))
            .where(AgentRunTask.status == status)
            .order_by(AgentRunTask.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_running_by_session(
        self, db: AsyncSession, session_id: str
    ) -> AgentRunTask | None:
        """Get the running task for a specific session."""
        result = await db.execute(
            select(AgentRunTask).where(
                AgentRunTask.session_id == session_id,
                AgentRunTask.status == RunStatus.RUNNING,
            )
        )
        return result.scalar_one_or_none()

    async def get_all_running_session_ids(self, db: AsyncSession) -> list[str]:
        """Get session IDs that have active running tasks."""
        result = await db.execute(
            select(AgentRunTask.session_id).where(
                AgentRunTask.status == RunStatus.RUNNING,
            )
        )
        return list(result.scalars().all())

    async def update_status(
        self, db: AsyncSession, task_id: uuid.UUID, status: str
    ) -> AgentRunTask | None:
        """Update the status of an agent run task."""
        result = await db.execute(
            select(AgentRunTask).where(AgentRunTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            return None

        task.status = status  # pyright: ignore
        db.add(task)
        await db.flush()
        await db.refresh(task)
        return task
