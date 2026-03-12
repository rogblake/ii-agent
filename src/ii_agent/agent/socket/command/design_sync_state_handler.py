"""Handler for syncing persisted design mode changes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.agent.events.stream import EventStream
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.projects.design.schemas import SyncStateRequest
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.agent.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class DesignSyncStateHandler(CommandHandler):
    """Socket handler for persisted design sync (replaces POST /projects/design/sync-state)."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.DESIGN_SYNC_STATE

    async def handle(self, content: Dict[str, Any], session_info: SessionInfo) -> None:
        session_id = session_info.id

        try:
            request = SyncStateRequest(**content)
        except Exception as exc:
            await self._send_error_event(
                session_id,
                message=f"Invalid design sync-state request: {exc}",
                error_type="validation_error",
            )
            return

        async def on_progress(**payload: Any) -> None:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.STATUS_UPDATE,
                    session_id=session_id,
                    content={
                        "operation": "design_mode_sync",
                        "progress": payload,
                        **payload,
                    },
                )
            )

        async def on_summary(summary: str) -> str | None:
            event = RealtimeEvent(
                type=EventType.AGENT_RESPONSE,
                session_id=session_id,
                content={"text": summary},
            )
            await self.send_event(event)
            return str(event.id)

        try:
            async with get_db_session_local() as db:
                result = await self.container.project_design_service.sync_persisted_design_changes(
                    db,
                    user_id=str(session_info.user_id),
                    request=request,
                    on_progress=on_progress,
                    on_summary=on_summary,
                )

            await self.send_event(
                RealtimeEvent(
                    type=EventType.SYSTEM,
                    session_id=session_id,
                    content={
                        "operation": "design_sync_state_complete",
                        "success": result.success,
                        "applied": result.applied,
                        "total": result.total,
                        "remaining": result.remaining,
                        "errors": result.errors,
                        "summary": result.summary,
                        "remaining_changes": [
                            change.model_dump() for change in result.remaining_changes
                        ],
                        "event_id": result.event_id,
                    },
                )
            )
        except Exception as exc:
            logger.exception("[DesignSyncStateHandler] Failed to sync persisted design changes")
            await self._send_error_event(
                session_id,
                message=f"Design sync-state failed: {exc}",
                error_type="design_sync_state_error",
            )
