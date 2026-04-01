"""Handler for design_get_state command."""

from __future__ import annotations

from ii_agent.core.container import ApplicationContainer
from ii_agent.core.db import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.realtime.events.app_events import SystemNotificationEvent
from ii_agent.realtime.handlers.base import BaseCommandHandler, CommandType
from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.realtime.schemas import DesignGetStateContent
from ii_agent.sessions.schemas import SessionInfo


class DesignGetStateHandler(BaseCommandHandler[DesignGetStateContent]):
    """Load persisted design-mode state for a session."""

    _content_type = DesignGetStateContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)

    def get_command_type(self) -> CommandType:
        return CommandType.DESIGN_GET_STATE

    async def handle(self, content: DesignGetStateContent, session_info: SessionInfo) -> None:
        design_service = self._container.project_design_service

        try:
            async with get_db_session_local() as db:
                result = await design_service.get_design_state(
                    db,
                    session_id=content.session_id,
                    user_id=str(session_info.user_id),
                )

            response_content = {
                "operation": "design_state_loaded",
                "success": True,
                "request_id": content.request_id,
                "session_id": content.session_id,
                "changes": [c.model_dump() for c in result.changes],
                "redo_changes": [c.model_dump() for c in result.redo_changes],
                "updated_at": result.updated_at,
            }
        except Exception as exc:
            logger.error("Failed to load design state for session {}: {}", content.session_id, exc)
            response_content = {
                "operation": "design_state_loaded",
                "success": False,
                "request_id": content.request_id,
                "session_id": content.session_id,
                "error": str(exc),
            }

        await self.send_event(
            SystemNotificationEvent(
                session_id=session_info.id,
                content=response_content,
                transient=True,
            )
        )
