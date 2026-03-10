from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
import uuid

from ii_agent.agent.types import AgentType
from ii_agent.core.events.models import EventType, RealtimeEvent
from ii_agent.core.events.stream import EventStream
from ii_agent.agent.runs.models import RunStatus
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.realtime.socket.schemas import (
    InitAgentContent,
    QueryCommandContent,
)
from ii_agent.realtime.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.agent.runtime.run.agent import RunCompletedEvent, RunOutput
from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
from ii_agent.agent.runtime.media import Image, File as UrlFile
from ii_agent.core.llm.token_record import TokenTracker
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class UserQueryHandler(CommandHandler):
    """Handler for query command that processes user queries and runs agents."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.QUERY

    async def handle(self, content: dict[str, Any], existing_session: SessionInfo) -> None:
        """Handle query processing by running the agent."""
        query_command = QueryCommandContent(**content)

        is_valid, session_info, llm_config = await self.validate_and_update_session(
            existing_session, query_command, min_credits=1.0
        )
        if not is_valid or not session_info:
            return

        await self._handle_query(query_command, session_info)

    async def _handle_query(
        self, query_command: QueryCommandContent, session_info: SessionInfo
    ) -> None:
        """Handle query processing."""
        execution_svc = self.container.execution_service

        # Generate milestone context if milestone execution is requested
        milestone_context = None
        if query_command.milestone_ids and query_command.plan_context:
            milestone_context = execution_svc.get_milestone_context(
                query_command.milestone_ids, query_command.plan_context
            )

        # Create task with lock via execution service
        result = await execution_svc.create_task_with_lock(
            session_info.id,
            {"text": query_command.text, "files": query_command.files},
            agent_run_service=self.container.agent_run_service,
            event_service=self.container.event_service,
        )
        if not result:
            return

        running_task = result.task
        await self.send_event(result.user_event)
        await self.send_event(result.processing_event)

        final_status = RunStatus.FAILED
        try:
            workspace_manager = WorkspaceManager(
                root=Path(self.container.config.workspace_path).resolve(),
                container_workspace=self.container.config.use_container_workspace,
            )

            init_content = InitAgentContent(
                model_id=query_command.model_id,
                tool_args=query_command.tool_args,
                source=query_command.source,
                thinking_tokens=query_command.thinking_tokens,
                agent_type=session_info.agent_type,
                metadata=query_command.metadata,
            )

            async with get_db_session_local() as db:
                llm_config = await self.container.llm_setting_service.get_llm_settings(
                    db,
                    session=session_info,
                    source=init_content.source,
                    model_id=init_content.model_id,
                )

            agent = await self.container.agent_service.create_agent_v1(
                session_info=session_info,
                llm_config=llm_config,
                workspace_manager=workspace_manager,
                agent_type=AgentType(session_info.agent_type) or AgentType.GENERAL,
                tool_args=init_content.tool_args,
                metadata=init_content.metadata,
                default_repository=query_command.github_repository,
            )

            # Prepare files via file service
            images, files = await self._prepare_files(query_command, session_info)

            # Build instruction text with milestone context if available
            instruction_text = query_command.text
            if milestone_context:
                instruction_text = (
                    f"{milestone_context}\n\nUser instruction: {query_command.text}"
                )

            event_stream = await agent.arun(
                instruction_text,
                stream=True,
                stream_events=True,
                run_id=str(running_task.id),
                images=images or None,
                files=files or None,
                yield_run_output=False,
            )

            async for event in event_stream:
                realtime_event = convert_agent_event_to_realtime(
                    event=event, session_id=session_info.id
                )
                if realtime_event:
                    await self.send_event(realtime_event)

                if isinstance(event, RunCompletedEvent):
                    # Determine final status - default to COMPLETED if event completed successfully
                    final_status = event.status or RunStatus.COMPLETED
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

                    # Direct billing — bypasses the broken MetricsSubscriber path
                    if event.metrics:
                        record = TokenTracker.from_agent_metrics(
                            event.metrics, event.model
                        )
                        async with get_db_session_local() as db:
                            await self.container.llm_billing_service.deduct_for_llm_usage(
                                db,
                                user_id=str(session_info.user_id),
                                session_id=str(session_info.id),
                                token_record=record,
                                is_user_model=llm_config.is_user_model(),
                            )
                            await db.commit()

                if isinstance(event, RunOutput):
                    # Use v1 Metrics format directly
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

            # Update milestones after run via execution service
            milestone_events = await execution_svc.update_milestones_after_run(
                session_info.id,
                query_command.milestone_ids,
                final_status,
                session_service=self.container.session_service,
                event_service=self.container.event_service,
            )
            for evt in milestone_events:
                await self.send_event(evt)

        except Exception as e:
            logger.error(f"Error processing query: {e}", exc_info=True)
            # Reset milestones to pending on error
            if query_command.milestone_ids:
                reset_events = await execution_svc.update_milestones_after_run(
                    session_info.id,
                    query_command.milestone_ids,
                    RunStatus.FAILED,
                    session_service=self.container.session_service,
                    event_service=self.container.event_service,
                )
                for evt in reset_events:
                    await self.send_event(evt)
            raise

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
            logger.info(f"Processed {len(images)} images for agent")
        if files:
            logger.info(f"Processed {len(files)} files for agent")

        return images, files
