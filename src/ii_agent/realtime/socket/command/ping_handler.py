"""Handler for ping command."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Any

from ii_agent.realtime.events.models import EventType, RealtimeEvent
from ii_agent.realtime.events.stream import EventStream
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.realtime.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class PingHandler(CommandHandler):
    """Handler for ping command."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.PING

    async def handle(self, content: Dict[str, Any], session_info: SessionInfo) -> None:
        """Handle ping message."""
        await self.send_event(
            RealtimeEvent(type=EventType.PONG, session_id=session_info.id, content={})
        )
