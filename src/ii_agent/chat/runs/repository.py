"""Repository layer for chat runs - data access only."""

from __future__ import annotations

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
        status: ChatRunStatus = ChatRunStatus.RUNNING,
    ) -> ChatRun:
        """Create a new chat run."""
        chat_run = ChatRun(
            session_id=str(session_id),
            status=status,
            user_message_id=user_message_id,
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
