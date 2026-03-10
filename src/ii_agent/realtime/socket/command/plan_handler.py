"""Handler for plan mode commands."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Any

from ii_agent.realtime.events.models import EventType, RealtimeEvent
from ii_agent.realtime.events.stream import EventStream
from ii_agent.engine.agents.models import AgentRunTask, RunStatus
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.engine.prompts.plan_mode_prompt import (
    get_plan_modification_suggestions_prompt,
    get_plan_modification_execute_prompt,
)
from ii_agent.realtime.socket.schemas import QueryCommandContent
from ii_agent.realtime.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.engine.runtime.factory.converter import convert_agent_event_to_realtime
from ii_agent.engine.runtime.run.agent import RunCompletedEvent, RunOutput
from ii_agent.engine.runtime.media import Image, File as UrlFile
from ii_agent.engine.runtime.tools.plan import MilestoneTool, PlanModificationSuggestionsTool
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class PlanHandler(CommandHandler):
    """Handler for plan mode commands.

    Uses the agent infrastructure with:
    - MilestoneTool for structured plan output
    - Plan-specific system prompt
    - Shared conversation history via State
    """

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.PLAN

    async def handle(self, content: Dict[str, Any], existing_session: SessionInfo) -> None:
        """Handle plan mode processing."""
        query_command = QueryCommandContent(**content)

        # Use shared validation from base class
        is_valid, session_info, llm_config = await self.validate_and_update_session(
            existing_session, query_command, min_credits=0.01
        )

        if not is_valid or not session_info or not llm_config:
            return

        await self._handle_plan(query_command, session_info, llm_config)

    async def _handle_plan(
        self,
        query_command: QueryCommandContent,
        session_info: SessionInfo,
        llm_config,
    ) -> None:
        """Handle plan mode processing."""
        plan_svc = self.container.plan_service
        execution_svc = self.container.execution_service

        # Create task with lock via execution service
        result = await execution_svc.create_task_with_lock(
            session_info.id,
            {
                "text": query_command.text,
                "files": query_command.files,
                "build_mode": query_command.build_mode,
            },
            agent_run_service=self.container.agent_run_service,
            event_service=self.container.event_service,
        )
        if not result:
            return

        running_task = result.task
        await self.send_event(result.user_event)
        await self.send_event(result.processing_event)

        try:
            # Route to appropriate handler
            if query_command.build_mode == "plan":
                # If a plan already exists, interpret plan-mode messages as plan
                # modifications instead of regenerating from scratch.
                if await plan_svc.has_existing_plan(
                    session_info.id, session_service=self.container.session_service
                ):
                    await self._handle_plan_modification(
                        query_command, session_info, llm_config, running_task
                    )
                else:
                    await self._handle_plan_generation(
                        query_command, session_info, llm_config, running_task
                    )
            elif query_command.build_mode == "modify_plan_suggestions":
                await self._handle_plan_modification_suggestions(
                    query_command, session_info, llm_config, running_task
                )
            elif query_command.build_mode == "modify_plan":
                await self._handle_plan_modification(
                    query_command, session_info, llm_config, running_task
                )
            else:
                await self._send_error_event(
                    str(session_info.id),
                    message="Invalid plan mode.",
                    error_type="invalid_mode_error",
                )

        except Exception as e:
            logger.error(f"Error in plan handler: {e}", exc_info=True)
            raise

    async def _handle_plan_generation(
        self,
        query_command: QueryCommandContent,
        session_info: SessionInfo,
        llm_config,
        running_task: AgentRunTask,
    ) -> None:
        """Handle plan generation using IIAgent with MilestoneTool."""
        logger.info(f"Handling plan mode for session {session_info.id}")

        try:
            # Send processing event
            await self.send_event(
                RealtimeEvent(
                    type=EventType.PROCESSING,
                    session_id=session_info.id,
                    run_id=running_task.id,
                    content={"message": "Generating project plan..."},
                )
            )

            workspace_manager = WorkspaceManager(
                root=Path(self.container.config.workspace_path).resolve(),
                container_workspace=self.container.config.use_container_workspace,
            )

            # Create MilestoneTool with event_stream for direct save/emit
            milestone_tool = MilestoneTool(
                session_id=session_info.id,
                session_service=self.container.session_service,
                event_service=self.container.event_service,
                event_stream=self.event_stream,
                session_info=session_info,
            )

            # Create plan agent
            agent = await self.container.agent_service.create_plan_agent_v1(
                session_info=session_info,
                llm_config=llm_config,
                workspace_manager=workspace_manager,
                plan_tools=[milestone_tool],
                tool_args=query_command.tool_args,
                metadata=query_command.metadata,
            )

            # Process files
            images, files = await self._prepare_files(query_command, session_info)

            # Build instruction text
            instruction_text = query_command.text

            # Run the agent
            event_stream = await agent.arun(
                instruction_text,
                stream=True,
                stream_events=True,
                run_id=str(running_task.id),
                images=images or None,
                files=files or None,
            )

            await self._process_agent_events(event_stream, session_info, running_task)

        except Exception as e:
            logger.error(f"Error in plan generation: {e}", exc_info=True)
            await self.container.plan_service.fail_task(
                running_task.id, agent_run_service=self.container.agent_run_service
            )
            await self._send_error_event(
                str(session_info.id),
                message=str(e),
                error_type="plan_error",
            )

    async def _handle_plan_modification_suggestions(
        self,
        query_command: QueryCommandContent,
        session_info: SessionInfo,
        llm_config,
        running_task: AgentRunTask,
    ) -> None:
        """Generate plan modification suggestions."""
        logger.info(f"Generating plan modification suggestions for session {session_info.id}")

        try:
            plan_data = await self.container.plan_service.get_plan_data(
                session_info.id, session_service=self.container.session_service
            )
            if not plan_data:
                await self.container.plan_service.fail_task(
                    running_task.id, agent_run_service=self.container.agent_run_service
                )
                await self._send_error_event(
                    str(session_info.id),
                    message="No plan found to modify.",
                    error_type="no_plan_error",
                )
                return

            await self.send_event(
                RealtimeEvent(
                    type=EventType.PROCESSING,
                    session_id=session_info.id,
                    run_id=running_task.id,
                    content={"message": "Generating modification suggestions..."},
                )
            )

            workspace_manager = WorkspaceManager(
                root=Path(self.container.config.workspace_path).resolve(),
                container_workspace=self.container.config.use_container_workspace,
            )

            # Get the suggestions prompt
            suggestions_prompt = get_plan_modification_suggestions_prompt(
                plan_summary=plan_data.get("summary", ""),
                milestones=plan_data.get("milestones", []),
            )

            # Create PlanModificationSuggestionsTool with event_stream for direct event emission
            suggestions_tool = PlanModificationSuggestionsTool(
                session_id=session_info.id,
                run_id=running_task.id,
                event_stream=self.event_stream,
                session_info=session_info,
            )

            # Create plan suggestions agent
            agent = await self.container.agent_service.create_plan_suggestions_agent_v1(
                session_info=session_info,
                llm_config=llm_config,
                workspace_manager=workspace_manager,
                system_prompt=suggestions_prompt,
                plan_tools=[suggestions_tool],
                tool_args=query_command.tool_args,
                metadata=query_command.metadata,
            )

            # Run agent to generate suggestions
            event_stream = await agent.arun(
                "Generate modification suggestions for the current plan.",
                stream=True,
                stream_events=True,
                run_id=str(running_task.id),
            )

            await self._process_agent_events(event_stream, session_info, running_task)

        except Exception as e:
            logger.error(f"Error generating modification suggestions: {e}", exc_info=True)
            await self.container.plan_service.fail_task(
                running_task.id, agent_run_service=self.container.agent_run_service
            )
            await self._send_error_event(
                str(session_info.id),
                message=str(e),
                error_type="plan_error",
            )

    async def _handle_plan_modification(
        self,
        query_command: QueryCommandContent,
        session_info: SessionInfo,
        llm_config,
        running_task: AgentRunTask,
    ) -> None:
        """Handle plan modification - shows suggestions if no text, executes modification if text provided."""
        logger.info(f"Handling modify plan for session {session_info.id}")

        # If user hasn't provided modification text, show suggestions
        if not query_command.text or query_command.text.strip() == "":
            await self._handle_plan_modification_suggestions(
                query_command, session_info, llm_config, running_task
            )
            return

        # Otherwise, execute the modification with the provided text
        try:
            plan_data = await self.container.plan_service.get_plan_data(
                session_info.id, session_service=self.container.session_service
            )
            if not plan_data:
                await self.container.plan_service.fail_task(
                    running_task.id, agent_run_service=self.container.agent_run_service
                )
                await self._send_error_event(
                    str(session_info.id),
                    message="No plan found to modify.",
                    error_type="no_plan_error",
                )
                return

            await self.send_event(
                RealtimeEvent(
                    type=EventType.PROCESSING,
                    session_id=session_info.id,
                    run_id=running_task.id,
                    content={"message": "Modifying plan..."},
                )
            )

            workspace_manager = WorkspaceManager(
                root=Path(self.container.config.workspace_path).resolve(),
                container_workspace=self.container.config.use_container_workspace,
            )

            # Create modification prompt with current plan context
            modification_prompt = get_plan_modification_execute_prompt(
                plan_summary=plan_data.get("summary", ""),
                milestones=plan_data.get("milestones", []),
                modification_request=query_command.text,
            )

            # Create MilestoneTool with event_stream for direct save/emit
            milestone_tool = MilestoneTool(
                session_id=session_info.id,
                session_service=self.container.session_service,
                event_service=self.container.event_service,
                event_stream=self.event_stream,
                session_info=session_info,
            )

            # Create plan agent with modification prompt
            agent = await self.container.agent_service.create_plan_agent_v1(
                session_info=session_info,
                llm_config=llm_config,
                workspace_manager=workspace_manager,
                system_prompt=modification_prompt,
                plan_tools=[milestone_tool],
                tool_args=query_command.tool_args,
                metadata=query_command.metadata,
            )

            # Process files
            images, files = await self._prepare_files(query_command, session_info)

            # Run agent with the modification request
            event_stream = await agent.arun(
                query_command.text,
                stream=True,
                stream_events=True,
                run_id=str(running_task.id),
                images=images or None,
                files=files or None,
            )

            await self._process_agent_events(event_stream, session_info, running_task)

        except Exception as e:
            logger.error(f"Error in plan modification: {e}", exc_info=True)
            await self.container.plan_service.fail_task(
                running_task.id, agent_run_service=self.container.agent_run_service
            )
            await self._send_error_event(
                str(session_info.id),
                message=str(e),
                error_type="modify_plan_error",
            )

    async def _process_agent_events(
        self,
        event_stream,
        session_info: SessionInfo,
        running_task: AgentRunTask,
    ) -> None:
        """Process agent events and emit realtime events."""
        async for event in event_stream:
            realtime_event = convert_agent_event_to_realtime(
                event=event, session_id=session_info.id
            )
            if realtime_event:
                await self.send_event(realtime_event)

            if isinstance(event, RunCompletedEvent):
                metrics_content = {"api_version": session_info.api_version}
                if event.metrics:
                    metrics_content["metrics"] = event.metrics.to_dict()
                    metrics_content["model_id"] = event.model
                await self.send_event(
                    RealtimeEvent(
                        type=EventType.METRICS_UPDATE,
                        session_id=session_info.id,
                        run_id=uuid.UUID(event.run_id) if event.run_id else None,
                        content=metrics_content,
                    )
                )

            if isinstance(event, RunOutput):
                # Update task status based on RunStatus
                from ii_agent.engine.runtime.run.agent import RunStatus as V1RunStatus

                v1_status = getattr(event, "status", None)
                status = (
                    RunStatus.ABORTED if v1_status == V1RunStatus.ABORTED else RunStatus.COMPLETED
                )
                async with get_db_session_local() as db:
                    await self.container.agent_run_service.update_task_status(
                        db, task_id=running_task.id, status=status
                    )
                    await db.commit()

                await self.send_event(
                    RealtimeEvent(
                        type=EventType.STREAM_COMPLETE,
                        session_id=session_info.id,
                        run_id=uuid.UUID(event.run_id) if event.run_id else None,
                        content={
                            "message": "Agent run completed",
                            "run_id": event.run_id,
                            "api_version": session_info.api_version,
                        },
                    )
                )

    async def _emit_plan_modification_suggestions(
        self,
        session_info: SessionInfo,
        run_id: uuid.UUID,
        message: str,
        suggestions: list,
    ) -> None:
        """Emit plan modification suggestions event."""
        await self.event_stream.publish(
            RealtimeEvent(
                type=EventType.PLAN_MODIFICATION_OPTIONS,
                session_id=session_info.id,
                run_id=run_id,
                content={
                    "message": message,
                    "suggestions": suggestions,
                },
            )
        )
        logger.info(f"Plan modification suggestions emitted for session {session_info.id}")

    async def _prepare_files(
        self,
        query_command: QueryCommandContent,
        session_info: SessionInfo,
    ) -> tuple[list[Image], list[UrlFile]]:
        """Prepare files for agent using FileService."""
        if not query_command.files:
            return [], []

        async with get_db_session_local() as db:
            image_dicts, file_dicts = await self.container.file_service.prepare_agent_files(
                db,
                file_ids=query_command.files,
                user_id=session_info.user_id,
                session_id=str(session_info.id),
            )

        images = [Image(url=i["url"], mime_type=i["mime_type"]) for i in image_dicts]
        files = [UrlFile(id=f["id"], url=f["url"], filename=f["filename"]) for f in file_dicts]

        if images:
            logger.info(f"Processed {len(images)} images for plan agent")
        if files:
            logger.info(f"Processed {len(files)} files for plan agent")

        return images, files
