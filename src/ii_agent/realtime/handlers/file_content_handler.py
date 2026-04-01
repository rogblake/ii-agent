"""Handler for file_content command."""

from __future__ import annotations

from ii_agent.realtime.events.app_events import FileContentEvent
from ii_agent.realtime.handlers.base import BaseCommandHandler, CommandType
from ii_agent.realtime.schemas import FileContentContent
from ii_agent.sessions.schemas import SessionInfo

class FileContentHandler(BaseCommandHandler[FileContentContent]):
    """Read one file from the sandbox via the workspace explorer service."""

    _content_type = FileContentContent

    def get_command_type(self) -> CommandType:
        return CommandType.FILE_CONTENT

    async def handle(self, content: FileContentContent, session_info: SessionInfo) -> None:
        payload = await self._container.workspace_explorer_service.read_file(
            session_info=session_info,
            path=content.path,
        )
        await self.send_event(
            FileContentEvent(
                session_id=session_info.id,
                content=payload,
            )
        )
