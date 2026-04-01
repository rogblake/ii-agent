"""Handler for ping command."""

from __future__ import annotations

from ii_agent.core.container import ApplicationContainer
from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.realtime.events.app_events import SystemPongEvent
from ii_agent.realtime.handlers.base import BaseCommandHandler, CommandType
from ii_agent.realtime.schemas import PingContent
from ii_agent.sessions.schemas import SessionInfo


class PingHandler(BaseCommandHandler[PingContent]):
    _content_type = PingContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)

    def get_command_type(self) -> CommandType:
        return CommandType.PING

    async def handle(self, content: PingContent, session_info: SessionInfo) -> None:
        await self.send_event(SystemPongEvent(session_id=session_info.id))
