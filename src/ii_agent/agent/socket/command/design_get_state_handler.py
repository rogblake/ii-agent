"""Handler for loading persisted design mode state."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.agent.events.stream import EventStream
from ii_agent.agent.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.projects.design.schemas import DesignStateGetRequest
from ii_agent.sessions.schemas import SessionInfo

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class DesignGetStateHandler(CommandHandler):
    """Socket handler for GET /projects/design/state."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.DESIGN_GET_STATE

    async def _send_response(
        self,
        target_session_id: Any,
        *,
        request_id: str | None,
        success: bool,
        error: str | None = None,
        **payload: Any,
    ) -> None:
        content: dict[str, Any] = {
            "operation": "design_state_loaded",
            "success": success,
            **payload,
        }
        if request_id:
            content["request_id"] = request_id
        if error:
            content["error"] = error
        await self.send_event(
            RealtimeEvent(
                type=EventType.SYSTEM,
                session_id=target_session_id,
                content=content,
            )
        )

    async def handle(self, content: Dict[str, Any], session_info: SessionInfo) -> None:
        request_id = content.get("request_id")
        if not isinstance(request_id, str):
            request_id = None

        try:
            request = DesignStateGetRequest(**content)
        except Exception as exc:
            await self._send_response(
                session_info.id,
                request_id=request_id,
                success=False,
                error=f"Invalid design state request: {exc}",
            )
            return

        try:
            async with get_db_session_local() as db:
                result = await self.container.project_design_service.get_design_state(
                    db,
                    session_id=request.session_id,
                    user_id=str(session_info.user_id),
                )

            await self._send_response(
                session_info.id,
                request_id=request_id,
                success=True,
                session_id=result.session_id,
                changes=[change.model_dump() for change in result.changes],
                redo_changes=[
                    change.model_dump() for change in result.redo_changes
                ],
                updated_at=result.updated_at,
            )
        except Exception as exc:
            logger.exception("[DesignGetStateHandler] Failed to load design state")
            await self._send_response(
                session_info.id,
                request_id=request_id,
                success=False,
                error=f"Failed to load design state: {exc}",
            )
