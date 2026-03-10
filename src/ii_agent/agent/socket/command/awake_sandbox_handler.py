"""Handler for awake_sandbox command."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Dict, Any

from ii_agent.core.events.models import EventType, RealtimeEvent
from ii_agent.core.events.stream import EventStream
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.agent.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)
from ii_agent.agent.sandboxes.schemas import SandboxStatus
from ii_agent.agent.sandboxes.exceptions import SandboxNotFoundException

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class AwakeSandboxHandler(CommandHandler):
    """Handler for awake sandbox command."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.AWAKE_SANDBOX

    async def handle(self, content: Dict[str, Any], session_info: SessionInfo) -> None:
        """Handle awake sandbox request."""
        status = SandboxStatus.NOT_INITIALIZED.value
        vscode_url = None

        try:
            async with get_db_session_local() as db:
                sandbox_manager = await self.container.sandbox_service.wake_up_sandbox_by_session(
                    db, uuid.UUID(session_info.id)
                )
                if sandbox_manager:
                    sandbox_info = await sandbox_manager.get_info()
                    status = sandbox_info.status.value
                    vscode_url = sandbox_info.vscode_url
        except SandboxNotFoundException:
            pass

        await self.send_event(
            RealtimeEvent(
                type=EventType.SANDBOX_STATUS,
                session_id=session_info.id,
                content={"status": status, "vscode_url": vscode_url},
            )
        )
