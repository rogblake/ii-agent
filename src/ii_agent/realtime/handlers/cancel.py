"""Handler for cancel command.

Extracted from ``server.socket.command.cancel_handler``.
"""

from ii_agent.core.redis import cancel
from ii_agent.core.container import ApplicationContainer
from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.tasks.types import RunStatus
from ii_agent.core.db import get_db_session_local
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.core.logger import logger
from ii_agent.realtime.handlers.base import (
    BaseCommandHandler,
    CommandType,
)
from ii_agent.realtime.schemas import CancelContent


class CancelHandler(BaseCommandHandler[CancelContent]):
    """Handler for cancel command."""

    _content_type = CancelContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)

    def get_command_type(self) -> CommandType:
        return CommandType.CANCEL

    async def handle(self, content: CancelContent, session: SessionInfo) -> None:
        """Handle cancel request -- signals the running agent to stop."""
        svc = self._container.run_task_service
        async with get_db_session_local() as db:
            last_task = await svc.get_last_by_session_id(db, session.id)
            if not last_task:
                await self._send_error_event(
                    session.id, message="Task Run not found"
                )
                return

            if last_task.status not in [RunStatus.RUNNING, RunStatus.PAUSED]:
                logger.info(
                    f"Cancel requested for non-running task {last_task.id} "
                    f"in status {last_task.status}, no action taken."
                )
                return

            await svc.transition_status(
                db, task_id=last_task.id, to_status=RunStatus.ABORTING
            )
            await db.commit()

        run_id = last_task.id
        cancelled = await cancel.cancel_run(str(run_id))

        if cancelled:
            logger.info(f"Run {run_id} cancelled for session {session.id}")
        else:
            logger.warning(f"Run {run_id} not found or already completed")
            await self._send_error_event(
                session.id,
                message="Run not found or already completed",
            )
