"""Handler for workspace_info command."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Any

from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.agent.events.stream import EventStream
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.agent.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class WorkspaceInfoHandler(CommandHandler):
    """Handler for workspace info command."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        """Initialize the workspace info handler with required dependencies.

        Args:
            event_stream: Event stream for publishing events
            container: Service container for dependency injection
        """
        super().__init__(event_stream=event_stream, container=container)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.WORKSPACE_INFO

    async def handle(self, content: Dict[str, Any], session_info: SessionInfo) -> None:
        """Handle workspace info request."""
        # Get workspace path from configuration
        workspace_path = str(self.container.config.workspace_path)

        await self.send_event(
            RealtimeEvent(
                type=EventType.WORKSPACE_INFO,
                session_id=session_info.id,
                content={"path": workspace_path},
            )
        )
