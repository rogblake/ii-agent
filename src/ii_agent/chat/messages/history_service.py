"""Chat message history service for fetching and building history responses."""

from __future__ import annotations

import uuid
import logging
from typing import List, Optional, Tuple, cast

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.messages.models import ChatMessage
from ii_agent.chat.messages.repository import ChatMessageRepository
from ii_agent.files.repository import FileRepository
from ii_agent.billing.usage.models import TokenUsage
from ii_agent.chat.api.schemas import (
    ChatMessageResponse,
    FileAttachmentResponse,
    MessageHistoryResponse,
)
from ii_agent.chat.types import MessageRoleType

logger = logging.getLogger(__name__)


def _normalize_content(content) -> list:
    """Normalize content to list format, handling old format for backward compat."""
    if not content:
        return []
    if isinstance(content, dict) and "parts" in content:
        return content["parts"]
    if isinstance(content, list):
        return content
    return []


class ChatMessageHistoryService:
    """Service for fetching and building chat message history responses."""

    def __init__(
        self,
        *,
        chat_repo: ChatMessageRepository,
        file_repo: FileRepository,
    ) -> None:
        self._repo = chat_repo
        self._file_repo = file_repo

    async def get_message_history(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        limit: int = 50,
        before: Optional[str] = None,
    ) -> Tuple[List[ChatMessage], bool]:
        """Get message history with pagination."""
        return await self._repo.get_history(db, session_id, limit, before)

    async def build_message_history_response(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        limit: int = 50,
        before: Optional[str] = None,
    ) -> MessageHistoryResponse:
        """Fetch message history and build the API response with file attachments."""
        messages, has_more = await self.get_message_history(
            db, session_id=session_id, limit=limit, before=before,
        )

        file_attach_map = await self._fetch_file_attachments(db, messages)

        message_responses = []
        for msg in messages:
            content_parts = _normalize_content(msg.content)
            files = []
            if msg.file_ids:
                for f in msg.file_ids:
                    if f in file_attach_map:
                        files.append(file_attach_map[f])

            message_responses.append(
                ChatMessageResponse(
                    id=str(msg.id),
                    role=cast(MessageRoleType, msg.role),
                    content=content_parts,
                    usage=TokenUsage(**dict(msg.usage)) if msg.usage is not None else None,
                    tokens=msg.tokens,
                    model=msg.model,
                    created_at=msg.created_at,
                    files=files,
                    finish_reason=msg.finish_reason,
                    metadata=msg.message_metadata,
                    provider_metadata=msg.provider_metadata,
                )
            )

        return MessageHistoryResponse(
            messages=message_responses,
            has_more=has_more,
            total_count=len(message_responses),
        )

    async def _fetch_file_attachments(
        self,
        db: AsyncSession,
        messages: List[ChatMessage],
    ) -> dict[uuid.UUID, FileAttachmentResponse]:
        """Fetch file attachments for all messages using a single query."""
        all_file_ids = set()
        for msg in messages:
            if msg.file_ids:
                all_file_ids.update(msg.file_ids)

        if not all_file_ids:
            return {}

        file_ids_str = [str(fid) if isinstance(fid, uuid.UUID) else fid for fid in all_file_ids]
        file_uploads = await self._file_repo.get_by_ids(db, file_ids_str)

        file_map: dict[uuid.UUID, FileAttachmentResponse] = {}
        for file_upload in file_uploads:
            file_id = uuid.UUID(file_upload.id)
            file_map[file_id] = FileAttachmentResponse(
                id=file_id,
                file_name=file_upload.file_name,
                file_size=file_upload.file_size,
                content_type=file_upload.content_type,
                created_at=file_upload.created_at,
            )

        return file_map
