"""Handler for syncing design mode changes to workspace files."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.agent.events.stream import EventStream
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.projects.design.schemas import SyncRequest
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.agent.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class DesignSyncHandler(CommandHandler):
    """Socket handler for design mode sync (replaces POST /projects/design/sync)."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.DESIGN_SYNC

    async def handle(self, content: Dict[str, Any], session_info: SessionInfo) -> None:
        session_id = session_info.id

        try:
            request = SyncRequest(**content)
        except Exception as exc:
            await self._send_error_event(
                session_id,
                message=f"Invalid design sync request: {exc}",
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

        try:
            async with get_db_session_local() as db:
                result = await self.container.project_design_service.sync_design_changes(
                    db,
                    user_id=str(session_info.user_id),
                    request=request,
                    on_progress=on_progress,
                )

            await self.send_event(
                RealtimeEvent(
                    type=EventType.SYSTEM,
                    session_id=session_id,
                    content={
                        "operation": "design_sync_complete",
                        "success": result.success,
                        "applied": result.applied,
                        "errors": result.errors,
                    },
                )
            )
        except Exception as exc:
            logger.exception("[DesignSyncHandler] Failed to sync design changes")
            await self._send_error_event(
                session_id,
                message=f"Design sync failed: {exc}",
                error_type="design_sync_error",
            )
