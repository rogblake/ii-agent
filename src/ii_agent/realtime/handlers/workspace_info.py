"""Handler for workspace_info command."""

from __future__ import annotations

from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.realtime.events.app_events import WorkspaceInfoEvent
from ii_agent.realtime.handlers.base import BaseCommandHandler, CommandType
from ii_agent.realtime.schemas import WorkspaceInfoContent
from ii_agent.sessions.schemas import SessionInfo


class WorkspaceInfoHandler(BaseCommandHandler[WorkspaceInfoContent]):
    _content_type = WorkspaceInfoContent

    def __init__(self, pubsub: AsyncIOPubSub) -> None:
        super().__init__(pubsub=pubsub, container=None)  # type: ignore[arg-type]

    def get_command_type(self) -> CommandType:
        return CommandType.WORKSPACE_INFO

    async def handle(self, content: WorkspaceInfoContent, session_info: SessionInfo) -> None:
        await self.send_event(
            WorkspaceInfoEvent(
                session_id=session_info.id,
                content={"workspace_path": ""},
            )
        )
