"""Handler for awake_sandbox command.

Extracted from ``server.socket.command.awake_sandbox_handler``.
"""

from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.realtime.events.app_events import SandboxStatusChangedEvent
from ii_agent.core.container import ApplicationContainer
from ii_agent.core.db import get_db_session_local
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.realtime.handlers.base import (
    BaseCommandHandler,
    CommandType,
)
from ii_agent.realtime.schemas import AwakeSandboxContent
from ii_agent.agents.sandboxes import E2BSandbox, SandboxStatus
from ii_agent.agents.sandboxes.repository import SandboxRepository


class AwakeSandboxHandler(BaseCommandHandler[AwakeSandboxContent]):
    """Handler for awake sandbox command."""

    _content_type = AwakeSandboxContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)

    def get_command_type(self) -> CommandType:
        return CommandType.AWAKE_SANDBOX

    async def handle(self, content: AwakeSandboxContent, session_info: SessionInfo) -> None:
        """Handle awake sandbox request."""
        status = SandboxStatus.NOT_INITIALIZED.value
        vscode_url = None

        container = self._container
        sandbox_repo = SandboxRepository()

        if session_info.api_version == "v1":
            async with get_db_session_local() as db:
                # First try to get sandbox by session_id
                sandbox_record = await sandbox_repo.get_by_session_id(db, session_info.id)

                if sandbox_record and sandbox_record.provider_sandbox_id:
                    # Connect to existing sandbox (this wakes it up)
                    sandbox_manager = await E2BSandbox.connect(
                        sandbox_id=str(sandbox_record.id),
                        session_id=str(sandbox_record.session_id),
                        provider_sandbox_id=sandbox_record.provider_sandbox_id,
                    )
                    sandbox_info = await sandbox_manager.get_info()
                    status = sandbox_info.status.value
                    vscode_url = sandbox_info.vscode_url
        else:
            sandbox_svc = container.sandbox_service
            await sandbox_svc.wake_up_sandbox_by_session(session_info.id)
            status = await sandbox_svc.get_sandbox_status_by_session(session_info.id)

        valid_statuses = {"starting", "ready", "paused", "terminated", "error"}
        event_status = status if status in valid_statuses else "starting"

        await self.send_event(
            SandboxStatusChangedEvent(
                session_id=session_info.id,
                content={"status": status, "vscode_url": vscode_url},
                status=event_status,
                vscode_url=vscode_url,
            )
        )
