"""Handler for continue_run command (Human-in-the-Loop)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict
from uuid import UUID

from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.agent.events.stream import EventStream
from ii_agent.billing.exceptions import InsufficientCreditsError
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.agent.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)
from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
from ii_agent.agent.runtime.run.agent import RunCompletedEvent, RunOutput
from ii_agent.agent.runtime.factory.factory import AgentFactory
from ii_agent.agent.types import AgentType
from ii_agent.agent.runtime.factory.tools import echo_message, generate_random_number
from ii_agent.agent.runtime.agent_sessions.store import AgentSessionStore
from ii_agent.agent.runtime.tools.connectors.connector_tool import ConnectorTool
from ii_agent.billing.usage.llm_invocation_repository import LLMInvocationRepository
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class ContinueRunHandler(CommandHandler):
    """Handler for continue_run command (Human-in-the-Loop).

    This handler receives user confirmation/rejection for paused agent runs
    and continues the execution with the user's response.

    Expected payload format:
    {
        "run_id": "uuid-string",
        "session_id": "uuid-string",
        "confirmed": true/false,
        "tool": {
            "tool_id": "optional-tool-id",
            "tool_name": "optional-tool-name"
        },
        "user_input": {
            "field_name": "field_value",
            ...
        }
    }

    For tools requiring user input:
    - The "user_input" field contains key-value pairs for user-provided input
    - These values are used to populate the user_input_schema fields
    - Example for plan modification: {"selected_suggestion_id": "suggestion-1"}
    """

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)
        self._agent_factory = AgentFactory(config=self.container.config)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.CONTINUE_RUN

    async def handle(self, content: Dict[str, Any], session_info: SessionInfo) -> None:
        """Handle the continue_run command.

        Args:
            content: Command content with run_id, session_id, confirmed, tool info
            session_info: Session information
        """
        # Extract required fields
        run_id = content.get("run_id")
        confirmed = content.get("confirmed")
        user_input = content.get("user_input", {})  # Optional user input values

        if run_id is None:
            await self._send_error_event(
                session_info.id,
                message="run_id is required",
                error_type="invalid_request",
            )
            return

        if confirmed is None:
            await self._send_error_event(
                session_info.id,
                message="confirmed field is required",
                error_type="invalid_request",
            )
            return

        # Send AGENT_CONTINUE event immediately to stop waiting for input
        await self.send_event(
            RealtimeEvent(
                type=EventType.AGENT_CONTINUE,
                session_id=UUID(str(session_info.id)),
                run_id=UUID(run_id),
                content={
                    "message": "Agent continuing...",
                    "confirmed": confirmed,
                },
            )
        )

        try:
            # Load the paused run from session store
            session_store = AgentSessionStore()
            run_response = await session_store.get_by_run_id(
                run_id=run_id, session_id=str(session_info.id)
            )

            if not run_response:
                await self._send_error_event(
                    session_info.id,
                    message=f"Run {run_id} not found",
                    error_type="run_not_found",
                )
                return

            # # Check if run has active requirements
            # if not run_response.active_requirements:
            #     await self._send_error_event(
            #         session_info.id,
            #         message=f"Run {run_id} has no active requirements",
            #         error_type="invalid_request",
            #     )
            #     return

            # Update requirements based on user response

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
                    # Update user_input_schema fields with provided values
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

            # Get LLM config for continuing the run
            async with get_db_session_local() as db:
                current_session = await self.container.session_service.get_session_by_id(
                    db, session_id=session_info.id
                )
                if not current_session:
                    await self._send_error_event(
                        session_info.id,
                        message="Session not found",
                        error_type="session_not_found",
                    )
                    return

                llm_config = await self.container.llm_setting_service.get_llm_settings(
                    db,
                    session=session_info,
                    source=None,
                    model_id=current_session.llm_setting_id,
                )

            connector_tool = ConnectorTool(user_id=str(session_info.user_id))

            # Create agent with same configuration
            agent = await self._agent_factory.create_agent(
                session_id=str(session_info.id),
                user_id=str(session_info.user_id),
                session_store=session_store,
                llm_config=llm_config,
                agent_type=AgentType(session_info.agent_type) or AgentType.GENERAL,
                tool_args={},  # TODO: retrieve this information from session metadata
                workspace_path=self.container.config.workspace_path,
                connector_tool=connector_tool,
            )

            # Add more test tools to support HITL
            agent.add_tool(generate_random_number)
            agent.add_tool(echo_message)
            # Send processing event
            await self.send_event(
                RealtimeEvent(
                    type=EventType.PROCESSING,
                    session_id=UUID(str(session_info.id)),
                    run_id=UUID(run_id),
                    content={
                        "message": "Resuming agent execution...",
                    },
                )
            )

            # Continue the run with updated requirements
            async for event in agent.acontinue_run(
                run_id=run_response.run_id,
                updated_tools=run_response.tools,
                stream=True,
                stream_events=True,
            ):
                # Convert v1 event to RealtimeEvent
                realtime_event = convert_agent_event_to_realtime(
                    event=event,
                    session_id=str(session_info.id),
                )

                if realtime_event:
                    await self.send_event(realtime_event)

                # Bill on RunCompletedEvent (streaming mode emits this, not RunOutput)
                if isinstance(event, RunCompletedEvent):
                    metrics_content = {"api_version": "v1"}
                    if event.metrics:
                        metrics_content["metrics"] = event.metrics.to_dict()
                        metrics_content["model_id"] = event.model
                    await self.send_event(
                        RealtimeEvent(
                            type=EventType.METRICS_UPDATE,
                            session_id=UUID(str(session_info.id)),
                            content=metrics_content,
                        )
                    )

        except InsufficientCreditsError as e:
            logger.warning(f"Insufficient credits for continue_run: {e}")
            await self._send_error_event(
                session_info.id,
                message=str(e),
                error_type="insufficient_credits",
            )
        except ValueError as e:
            logger.error(f"ValueError in continue_run: {str(e)}")
            await self._send_error_event(
                session_info.id,
                message=str(e),
                error_type="validation_error",
            )
        except Exception as e:
            logger.error(f"Error in continue_run handler: {str(e)}", exc_info=True)
            await self._send_error_event(
                session_info.id,
                message=f"Failed to continue run: {str(e)}",
                error_type="execution_error",
            )
