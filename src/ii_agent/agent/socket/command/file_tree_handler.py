"""Handler for file_tree command."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.agent.events.stream import EventStream
from ii_agent.agent.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)
from ii_agent.sessions.schemas import SessionInfo

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class FileTreeHandler(CommandHandler):
    """Return the project's file tree and start a watcher if not already running."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.FILE_TREE

    async def handle(self, content: dict[str, Any], session_info: SessionInfo) -> None:
        await self.container.workspace_explorer_service.ensure_watching(
            session_info=session_info
        )
        payload = await self.container.workspace_explorer_service.get_tree(
            session_info=session_info
        )
        await self.send_event(
            RealtimeEvent(
                type=EventType.FILE_TREE,
                session_id=session_info.id,
                content=payload,
            )
        )
