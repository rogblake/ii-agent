"""Repository for ChatMessage data access."""

import logging
import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.messages.models import ChatMessage

logger = logging.getLogger(__name__)


class ChatMessageRepository:
    """Data access layer for ChatMessage."""

    async def create(self, db: AsyncSession, message: ChatMessage) -> ChatMessage:
        """Persist a new ChatMessage and return it refreshed."""
        db.add(message)
        await db.flush()
        await db.refresh(message)
        return message

    async def list_by_session(
        self, db: AsyncSession, session_id: uuid.UUID, limit: int = 50
    ) -> List[ChatMessage]:
        """List messages for a session in chronological order."""
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_after_id(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        after_message_id: uuid.UUID,
        limit: int = 1000,
    ) -> List[ChatMessage]:
        """List messages created after a specific message ID."""
        result = await db.execute(
            select(ChatMessage.created_at).where(ChatMessage.id == after_message_id)
        )
        after_timestamp = result.scalar_one_or_none()

        if not after_timestamp:
            return await self.list_by_session(db, session_id, limit)

        return await self.list_after_timestamp(db, session_id, after_timestamp, limit)

    async def list_after_timestamp(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        after_timestamp: datetime,
        limit: int = 1000,
    ) -> List[ChatMessage]:
        """List messages created after a specific timestamp."""
        result = await db.execute(
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.created_at > after_timestamp,
            )
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_incomplete(self, db: AsyncSession, parent_message_id: uuid.UUID) -> None:
        """Mark child messages as incomplete (best-effort)."""
        try:
            await db.execute(
                update(ChatMessage)
                .where(ChatMessage.parent_message_id == parent_message_id)
                .values(is_finished=False)
            )
            await db.flush()
            logger.info(
                f"Marked children as incomplete for message_id: {parent_message_id}"
            )
        except Exception as e:
            logger.error(f"Failed to mark messages as incomplete: {e}", exc_info=True)

    async def get_history(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        limit: int = 50,
        before: Optional[str] = None,
    ) -> Tuple[List[ChatMessage], bool]:
        """Get message history with pagination (newest first, then reversed)."""
        query = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit + 1)
        )

        if before:
            before_msg = await db.get(ChatMessage, before)
            if before_msg:
                query = query.where(ChatMessage.created_at < before_msg.created_at)

        result = await db.execute(query)
        messages = list(result.scalars().all())

        has_more = len(messages) > limit
        if has_more:
            messages = messages[:limit]

        messages.reverse()
        return messages, has_more

    async def delete_by_session(self, db: AsyncSession, session_id: uuid.UUID) -> int:
        """Delete all messages in a session. Returns deleted count."""
        result = await db.execute(
            delete(ChatMessage).where(ChatMessage.session_id == session_id)
        )
        await db.flush()
        return result.rowcount

    async def delete_from_message(
        self, db: AsyncSession, session_id: uuid.UUID, message_id: uuid.UUID
    ) -> int:
        """Delete a message and all subsequent messages in a session.

        Finds the target message's created_at, then deletes it and all messages
        created at or after that timestamp in the same session.
        """
        result = await db.execute(
            select(ChatMessage.created_at).where(
                ChatMessage.id == message_id,
                ChatMessage.session_id == session_id,
            )
        )
        target_ts = result.scalar_one_or_none()
        if target_ts is None:
            return 0

        result = await db.execute(
            delete(ChatMessage).where(
                ChatMessage.session_id == session_id,
                ChatMessage.created_at >= target_ts,
            )
        )
        await db.flush()
        return result.rowcount

    async def get_last_by_session(self, db: AsyncSession, session_id: uuid.UUID) -> Optional[ChatMessage]:
        """Get the most recent message in a session."""
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_running_by_session(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> Optional[ChatMessage]:
        """Find an incomplete assistant message (i.e. a 'running' chat turn)."""
        result = await db.execute(
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == "assistant",
                ChatMessage.is_finished == False,  # noqa: E712
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_last_assistant_by_session(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> Optional[ChatMessage]:
        """Get the most recent assistant message for a session."""
        result = await db.execute(
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == "assistant",
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_recent(self, db: AsyncSession, session_id: uuid.UUID, limit: int) -> List[ChatMessage]:
        """Get recent messages in chronological order."""
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        messages = list(result.scalars().all())
        messages.reverse()
        return messages
