"""Repository layer for chat runs - data access only."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.runs.models import ChatRun, ChatRunStatus


class ChatRunRepository:
    """Data access layer for ChatRun model."""

    async def create(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        user_message_id: uuid.UUID | None = None,
        model_id: str | None = None,
        status: ChatRunStatus = ChatRunStatus.RUNNING,
    ) -> ChatRun:
        """Create a new chat run."""
        chat_run = ChatRun(
            session_id=str(session_id),
            status=status,
            user_message_id=user_message_id,
            model_id=model_id,
            started_at=datetime.now(timezone.utc),
        )
        db.add(chat_run)
        await db.flush()
        await db.refresh(chat_run)
        return chat_run

    async def find_running_by_session(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> ChatRun | None:
        """Find a running chat run for a session."""
        result = await db.execute(
            select(ChatRun)
            .where(
                ChatRun.session_id == str(session_id),
                ChatRun.status == ChatRunStatus.RUNNING,
            )
            .order_by(ChatRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def set_provider(
        self,
        db: AsyncSession,
        *,
        chat_run: ChatRun,
        provider: str | None,
        model_id: str | None = None,
    ) -> ChatRun:
        """Persist resolved provider/model information for a run."""
        chat_run.provider = provider
        if model_id is not None:
            chat_run.model_id = model_id
        await db.flush()
        return chat_run

    async def complete(
        self,
        db: AsyncSession,
        *,
        chat_run: ChatRun,
        assistant_message_id: uuid.UUID | None,
        finish_reason: str | None,
    ) -> ChatRun:
        """Mark a run as completed and persist completion metadata."""
        chat_run.status = ChatRunStatus.COMPLETED
        chat_run.assistant_message_id = assistant_message_id
        chat_run.finish_reason = finish_reason
        chat_run.completed_at = datetime.now(timezone.utc)
        await db.flush()
        return chat_run

    async def fail(
        self,
        db: AsyncSession,
        *,
        chat_run: ChatRun,
        status: ChatRunStatus,
        error_message: str | None = None,
        error_code: str | None = None,
    ) -> ChatRun:
        """Mark a run as failed or aborted."""
        chat_run.status = status
        chat_run.error_message = error_message
        chat_run.error_code = error_code
        chat_run.completed_at = datetime.now(timezone.utc)
        await db.flush()
        return chat_run
