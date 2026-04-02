"""Handler for slide_deck_sync_state command."""

from __future__ import annotations

from ii_agent.content.slides.design.schemas import SlideDeckSyncStateRequest
from ii_agent.core.container import ApplicationContainer
from ii_agent.core.db import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.realtime.events.app_events import (
    AgentResponseEvent,
    AgentStatusUpdateEvent,
    ErrorCode,
    SystemNotificationEvent,
)
from ii_agent.realtime.handlers.base import BaseCommandHandler, CommandType
from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.realtime.schemas import SlideDeckSyncStateContent
from ii_agent.sessions.schemas import SessionInfo


class SlideDeckSyncStateHandler(BaseCommandHandler[SlideDeckSyncStateContent]):
    """Sync persisted slide design-mode changes to source files."""

    _content_type = SlideDeckSyncStateContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)

    def get_command_type(self) -> CommandType:
        return CommandType.SLIDE_DECK_SYNC_STATE

    async def handle(self, content: SlideDeckSyncStateContent, session_info: SessionInfo) -> None:
        slide_design_service = self._container.slide_design_service
        session_uuid = session_info.id

        async def on_progress(**payload: object) -> None:
            await self.send_event(
                AgentStatusUpdateEvent(
                    session_id=session_uuid,
                    content={
                        "operation": "design_mode_sync",
                        "progress": payload,
                        **payload,
                    },
                )
            )

        async def on_summary(summary: str) -> str | None:
            async with get_db_session_local() as db:
                event_service = self._container.event_service
                evt = AgentResponseEvent(
                    session_id=session_uuid,
                    content={"text": summary},
                )
                saved = await event_service.save_event(
                    db,
                    session_id=session_uuid,
                    event=evt,
                )
                return str(saved.id)

        try:
            request = SlideDeckSyncStateRequest(
                session_id=content.session_id,
                presentation_name=content.presentation_name,
            )

            async with get_db_session_local() as db:
                result = await slide_design_service.sync_persisted_slide_deck_changes(
                    db,
                    request=request,
                    user_id=str(session_info.user_id),
                    on_progress=on_progress,
                    on_summary=on_summary,
                )

            response_content = {
                "operation": "slide_deck_sync_state_complete",
                "success": result.success,
                "applied": result.applied,
                "total": result.total,
                "remaining": result.remaining,
                "errors": result.errors,
                "summary": result.summary,
                "remaining_changes": [c.model_dump() for c in result.remaining_changes],
                "event_id": result.event_id,
                "session_id": str(session_uuid),
            }
        except Exception as exc:
            logger.error(
                "Failed to sync slide deck state for session {}: {}",
                content.session_id,
                exc,
            )
            await self._send_error_event(
                session_uuid,
                error_code=ErrorCode.SLIDE_DECK_SYNC_STATE_ERROR,
                message=f"Slide deck sync failed: {exc}",
            )
            return

        await self.send_event(
            SystemNotificationEvent(
                session_id=session_uuid,
                content=response_content,
            )
        )
