"""Service layer for chat runs - business logic only."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.runs.repository import ChatRunRepository
from ii_agent.chat.runs.models import ChatRun, ChatRunStatus


class ChatRunService:
    """Service for managing chat run lifecycle."""

    def __init__(self, *, repo: ChatRunRepository) -> None:
        self._repo = repo

    async def create_run(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        user_message_id: uuid.UUID | None = None,
        status: ChatRunStatus = ChatRunStatus.RUNNING,
    ) -> ChatRun:
        """Create a new chat run."""
        return await self._repo.create(
            db, session_id=session_id, user_message_id=user_message_id, status=status
        )

    async def find_running_for_cancel(
        self, db: AsyncSession, *, session_id: uuid.UUID
    ) -> ChatRun | None:
        """Find a running chat run for cancellation."""
        return await self._repo.find_running_by_session(db, session_id)
