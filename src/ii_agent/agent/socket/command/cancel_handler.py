"""Handler for cancel command."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Any

from ii_agent.core.redis import cancel
from ii_agent.agent.events.stream import EventStream
from ii_agent.agent.runs.models import AgentRunTask, RunStatus
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.agent.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)

from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class CancelHandler(CommandHandler):
    """Handler for cancel command."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.CANCEL

    async def handle(self, content: Dict[str, Any], session_info: SessionInfo) -> None:
        """Handle cancel request — signals the running agent to stop.

        When the run is PAUSED (waiting for tool confirmation), the normal
        streaming loop has already ended, so this handler only marks the run
        as aborting and relies on persisted per-call billing state.
        """
        async with get_db_session_local() as db:
            last_task: (
                AgentRunTask | None
            ) = await self.container.agent_run_service.get_last_by_session_id(
                db=db, session_id=session_info.id
            )
            if not last_task:
                await self._send_error_event(session_info.id, message="Task Run not found")
                return

            if last_task.status not in [RunStatus.RUNNING.value, RunStatus.PAUSED.value]:
                logger.info(
                    f"Cancel requested for non-running task {last_task.id} "
                    f"in status {last_task.status}, no action taken."
                )
                return

            original_status = last_task.status
            last_task.status = RunStatus.ABORTING.value
            await db.commit()

        run_id = last_task.id
        cancelled = await cancel.cancel_run(str(run_id))

        if cancelled:
            logger.info(f"Run {run_id} cancelled for session {session_info.id}")
        else:
            logger.warning(f"Run {run_id} not found or already completed")
            await self._send_error_event(
                session_info.id,
                message="Run not found or already completed",
            )

        if original_status == RunStatus.PAUSED.value:
            logger.info(
                "Paused run {} cancelled; per-call billing already settled in runtime", run_id
            )
