"""Handler for sandbox_status command."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Any

from ii_agent.realtime.events.models import EventType, RealtimeEvent
from ii_agent.realtime.events.stream import EventStream
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.realtime.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)
from ii_agent.agent.sandboxes.schemas import SandboxStatus
from ii_agent.agent.sandboxes.e2b import E2BSandboxManager

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class SandboxStatusHandler(CommandHandler):
    """Handler for sandbox status command."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.SANDBOX_STATUS

    async def handle(self, content: Dict[str, Any], session_info: SessionInfo) -> None:
        """Handle get sandbox status request."""
        status = SandboxStatus.NOT_INITIALIZED.value
        vscode_url = None
        async with get_db_session_local() as db:
            sandbox_record = await self.container.sandbox_service.resolve_sandbox_for_session(
                db, session_info.id, session_service=self.container.session_service
            )

            if sandbox_record and sandbox_record.provider_sandbox_id:
                sandbox_manager = await E2BSandboxManager.from_sandbox_record(
                    sandbox_record=sandbox_record
                )
                if not sandbox_manager:
                    return
                sandbox_info = await sandbox_manager.get_info()
                status = sandbox_info.status.value
                vscode_url = sandbox_info.vscode_url

        await self.send_event(
            RealtimeEvent(
                type=EventType.SANDBOX_STATUS,
                session_id=session_info.id,
                content={"status": status, "vscode_url": vscode_url},
            )
        )
