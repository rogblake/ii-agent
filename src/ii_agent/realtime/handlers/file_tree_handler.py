"""Handler for file_tree command."""

from __future__ import annotations

from ii_agent.realtime.events.app_events import FileTreeEvent
from ii_agent.realtime.handlers.base import BaseCommandHandler, CommandType
from ii_agent.realtime.schemas import FileTreeContent
from ii_agent.sessions.schemas import SessionInfo


class FileTreeHandler(BaseCommandHandler[FileTreeContent]):
    """Return the project's file tree and start a watcher if not already running."""

    _content_type = FileTreeContent

    def get_command_type(self) -> CommandType:
        return CommandType.FILE_TREE

    async def handle(self, content: FileTreeContent, session_info: SessionInfo) -> None:
        explorer = self._container.workspace_explorer_service
        await explorer.ensure_watching(session_info=session_info)
        payload = await explorer.get_tree(session_info=session_info)
        await self.send_event(
            FileTreeEvent(
                session_id=session_info.id,
                content=payload,
            )
        )
