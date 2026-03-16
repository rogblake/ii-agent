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
        model_id: str | None = None,
        status: ChatRunStatus = ChatRunStatus.RUNNING,
    ) -> ChatRun:
        """Create a new chat run."""
        return await self._repo.create(
            db,
            session_id=session_id,
            user_message_id=user_message_id,
            model_id=model_id,
            status=status,
        )

    async def get_last_by_session_id(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> ChatRun | None:
        """Get the most recent chat run for a session."""
        return await self._repo.find_last_by_session_id(db, session_id)

    async def find_running_for_cancel(
        self, db: AsyncSession, *, session_id: uuid.UUID
    ) -> ChatRun | None:
        """Find a running chat run for cancellation."""
        return await self._repo.find_running_by_session(db, session_id)

    async def set_provider(
        self,
        db: AsyncSession,
        *,
        chat_run: ChatRun,
        provider: str | None,
        model_id: str | None = None,
    ) -> ChatRun:
        """Persist resolved provider/model information."""
        return await self._repo.set_provider(
            db,
            chat_run=chat_run,
            provider=provider,
            model_id=model_id,
        )

    async def complete_run(
        self,
        db: AsyncSession,
        *,
        chat_run: ChatRun,
        assistant_message_id: uuid.UUID | None,
        finish_reason: str | None,
    ) -> ChatRun:
        """Mark a chat run as completed."""
        return await self._repo.complete(
            db,
            chat_run=chat_run,
            assistant_message_id=assistant_message_id,
            finish_reason=finish_reason,
        )

    async def fail_run(
        self,
        db: AsyncSession,
        *,
        chat_run: ChatRun,
        status: ChatRunStatus,
        error_message: str | None = None,
        error_code: str | None = None,
    ) -> ChatRun:
        """Mark a chat run as failed or aborted."""
        return await self._repo.fail(
            db,
            chat_run=chat_run,
            status=status,
            error_message=error_message,
            error_code=error_code,
        )
