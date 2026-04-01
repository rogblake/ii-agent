"""Handler for continue_run command (Human-in-the-Loop).

Extracted from ``server.socket.command.continue_run_handler``.
"""

from __future__ import annotations

from uuid import UUID

from ii_agent.agents.factory.agent import agent_factory
from ii_agent.agents.sessions import AgentSessionStore
from ii_agent.agents.types import AgentType
from ii_agent.core.container import ApplicationContainer
from ii_agent.core.db import get_db_session_local, get_session_factory
from ii_agent.core.logger import logger
from ii_agent.realtime.events.app_events import (
    AgentContinueEvent,
    AgentProcessingEvent,
    ErrorCode,
)
from ii_agent.realtime.handlers.base import BaseCommandHandler, CommandType
from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.realtime.schemas import ContinueRunContent
from ii_agent.sessions.schemas import SessionInfo


class ContinueRunHandler(BaseCommandHandler[ContinueRunContent]):
    """Handler for continue_run command (Human-in-the-Loop)."""

    _content_type = ContinueRunContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)

    def get_command_type(self) -> CommandType:
        return CommandType.CONTINUE_RUN

    async def handle(self, content: ContinueRunContent, session_info: SessionInfo) -> None:
        """Handle the continue_run command."""
        # Only work for v1 API version
        if session_info.api_version != "v1":
            await self._send_error_event(
                session_info.id,
                error_code=ErrorCode.UNSUPPORTED_API_VERSION,
            )
            return

        # Extract required fields
        run_id = content.run_id
        confirmed = content.confirmed
        user_input = content.user_input

        # Send AGENT_CONTINUE event immediately to stop waiting for input
        await self.send_event(
            AgentContinueEvent(
                session_id=UUID(str(session_info.id)),
                content={
                    "message": "Agent continuing...",
                    "confirmed": confirmed,
                    "run_id": run_id,
                },
            )
        )

        try:
            # Load the paused run from session store
            session_store = AgentSessionStore(session_maker=get_session_factory())
            run_response = await session_store.get_by_run_id(
                run_id=run_id, session_id=str(session_info.id)
            )

            if not run_response:
                await self._send_error_event(
                    session_info.id,
                    error_code=ErrorCode.RUN_NOT_FOUND,
                    message=f"Run {run_id} not found",
                )
                return

            # Handle tools requiring confirmation
            for _t in run_response.tools_requiring_confirmation:
                if confirmed:
                    _t.confirmed = True
                    logger.info(f"User confirmed requirement for run {run_id}")
                else:
                    _t.confirmed = False
                    logger.info(f"User rejected requirement for run {run_id}")

            # Handle tools requiring user input
            for _t in run_response.tools_requiring_user_input:
                if confirmed and user_input:
                    if _t.user_input_schema:
                        for field in _t.user_input_schema:
                            if field.name in user_input:
                                field.value = user_input[field.name]
                                logger.info(
                                    f"User provided input for field '{field.name}' in run {run_id}"
                                )
                    _t.answered = True
                else:
                    _t.answered = False
                    logger.info(f"User did not provide input for run {run_id}")

            # Get model config for continuing the run
            if not session_info.model_setting_id:
                raise ValueError("Session has no model_setting_id for continue_run")
            async with get_db_session_local() as db:
                llm_config = await self._container.model_setting_service.resolve_config_by_setting_id(
                    db, setting_id=session_info.model_setting_id
                )

            # Create agent with same configuration (matches query handler pattern)
            agent = await agent_factory.create_agent(
                user_id=str(session_info.user_id),
                session_id=str(session_info.id),
                llm_config=llm_config,
                agent_type=AgentType(session_info.agent_type)
                if session_info.agent_type
                else AgentType.GENERAL,
                session_store=session_store,
            )

            # Send processing event
            await self.send_event(
                AgentProcessingEvent(
                    session_id=UUID(str(session_info.id)),
                    message="Resuming agent execution...",
                    content={
                        "message": "Resuming agent execution...",
                        "run_id": run_id,
                    },
                )
            )

            # Continue the run with updated requirements
            event_stream = agent.acontinue_run(
                run_id=run_response.run_id,
                updated_tools=run_response.tools,
                stream=True,
                stream_events=True,
            )

            await self.process_agent_event_stream(
                event_stream, session_info, run_id=UUID(run_response.run_id),
                is_user_key=llm_config.is_user_model(),
            )

        except ValueError as e:
            logger.error(f"ValueError in continue_run: {str(e)}")
            await self._send_error_event(
                session_info.id,
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(e),
            )
        except Exception as e:
            logger.error(f"Error in continue_run handler: {str(e)}", exc_info=True)
            await self._send_error_event(
                session_info.id,
                error_code=ErrorCode.EXECUTION_ERROR,
                message=f"Failed to continue run: {str(e)}",
            )
