"""Chat service - thin orchestrator for chat conversations."""

from __future__ import annotations

import logging
import uuid
from typing import AsyncIterator, Dict, Optional, TYPE_CHECKING
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import Settings
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.chat.types import (
    BinaryContent,
    CouncilMemberOutput,
    CouncilSynthesis,
    Message,
    TextContent,
    MessageRole,
    EventType,
    FinishReason,
)
from ii_agent.chat.api.schemas import ChatMessageRequest, SessionMetadata
from ii_agent.chat.exceptions import AnthropicImageTooLargeError
from ii_agent.chat.llm import LLMProviderFactory
from ii_agent.chat.messages.service import MessageService
from ii_agent.chat.media.orchestrator import MediaOrchestrator
from ii_agent.chat.application.context_service import ContextWindowManager
from ii_agent.chat.application.file_processing_service import ChatFileProcessor
from ii_agent.chat.application.tool_service import ChatToolService
from ii_agent.chat.application.turn_loop_service import LLMTurnLoopService
from ii_agent.chat.messages.history_service import ChatMessageHistoryService
from ii_agent.chat.application.council_service import CouncilService, MIN_COUNCIL_MODELS
from ii_agent.sessions.models import Session
from ii_agent.sessions.repository import SessionRepository
from ii_agent.chat.runs.models import ChatRunStatus
from ii_agent.chat.runs.service import ChatRunService
from ii_agent.billing.credits.service import CreditService
from ii_agent.settings.llm.service import get_system_llm_config
from ii_agent.core.redis import cancel
from ii_agent.chat.exceptions import ModelNotFoundError
from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.sessions.title_service import SessionTitleService

if TYPE_CHECKING:
    from ii_agent.chat.messages.repository import ChatMessageRepository
    from ii_agent.core.container import ServiceContainer

logger = logging.getLogger(__name__)


class ChatService:
    """Thin orchestrator for chat conversations."""

    def __init__(
        self,
        *,
        file_processor: ChatFileProcessor,
        tool_service: ChatToolService,
        llm_loop: LLMTurnLoopService,
        message_history: ChatMessageHistoryService,
        message_service: MessageService,
        session_repo: SessionRepository,
        chat_run_service: ChatRunService,
        llm_setting_service,
        credit_service: CreditService | None = None,
        container: ServiceContainer,
        title_service: SessionTitleService,
    ) -> None:
        self._file_processor = file_processor
        self._tool_service = tool_service
        self._llm_loop = llm_loop
        self._message_history = message_history
        self._message_service = message_service
        self._session_repo = session_repo
        self._chat_run_service = chat_run_service
        self._llm_setting_service = llm_setting_service
        self._credit_service = credit_service
        self._container = container
        self._title_service = title_service

    @staticmethod
    def _chat_run_error_code(exc: Exception, *, is_cancelled: bool) -> str:
        """Normalize chat-run error codes for telemetry."""
        if is_cancelled:
            return "cancelled"
        return exc.__class__.__name__

    async def create_chat_session(
        self, db: AsyncSession, *, user_message: str, user_id: str, model_id: str
    ) -> SessionMetadata:
        session_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        session_name, title_pending = self._title_service.build_initial_title(
            user_message,
            80,
        )

        session = Session(
            id=session_id,
            user_id=user_id,
            name=session_name,
            status="active",
            agent_type="chat",
            app_kind="chat",
            created_at=created_at,
            updated_at=created_at,
            session_metadata=SessionTitleService.set_title_pending(
                None,
                title_pending,
            ),
        )
        session = await self._session_repo.create(db, session)
        await db.commit()

        logger.info(f"Created chat session {session_id} for user {user_id}")

        if title_pending:
            self._title_service.schedule_title_update(session_id, user_message)

        return SessionMetadata(
            session_id=session_id,
            name=session.name,
            title_pending=title_pending,
            status="active",
            agent_type="chat",
            model_id=model_id,
            created_at=created_at.isoformat(),
        )

    async def update_session_name_if_untitled(
        self, db: AsyncSession, *, session_id: str, query: str
    ) -> None:
        session = await self._session_repo.get_by_id(db, session_id)
        if not session:
            return

        if session.name == "Untitled":
            session.name, title_pending = self._title_service.build_initial_title(
                query,
                80,
            )
            session.session_metadata = SessionTitleService.set_title_pending(
                getattr(session, "session_metadata", None),
                title_pending,
            )
            await db.flush()
            if title_pending:
                self._title_service.schedule_title_update(session_id, query)
                logger.info(f"Scheduled background title update for session {session_id}")

    async def validate_session_access(
        self, db: AsyncSession, *, session_id: str, user_id: str
    ) -> None:
        session = await self._session_repo.get_by_id(db, session_id)
        if not session or session.user_id != user_id:
            raise SessionNotFoundError("Session not found or access denied")

    async def validate_public_session_access(
        self, db: AsyncSession, *, session_id: str
    ) -> None:
        session = await self._session_repo.get_public_by_id(db, session_id)
        if not session:
            raise SessionNotFoundError("Session not found or not public")

    async def validate_model_for_chat(
        self, db: AsyncSession, *, model_id: str, user_id: str
    ) -> None:
        all_models = await self._llm_setting_service.get_all_available_models(
            db,
            user_id=user_id,
        )
        model_info = next((m for m in all_models.models if m.id == model_id), None)
        if not model_info:
            raise ModelNotFoundError(f"Model not found: {model_id}")

    async def get_llm_config(
        self, db: AsyncSession, *, model_id: str, user_id: str
    ) -> LLMConfig:
        try:
            return await self._llm_setting_service.get_user_llm_config(
                db,
                model_id=model_id,
                user_id=user_id,
            )
        except ValueError:
            return get_system_llm_config(model_id=model_id, config=self._file_processor._config)

    async def build_message_history_response(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        limit: int = 50,
        before: Optional[str] = None,
    ):
        """Delegate to message history service."""
        return await self._message_history.build_message_history_response(
            db, session_id=session_id, limit=limit, before=before,
        )

    async def stream_chat_response(
        self, db: AsyncSession, *, chat_request: ChatMessageRequest, user_id: str
    ) -> AsyncIterator[Dict]:
        """Stream chat response with tool execution loop.

        Orchestrates: context loading, file processing, tool setup, LLM turn loop.
        """
        session_id = str(chat_request.session_id)
        default_tools = {
            "web_search": True,
            "image_search": True,
            "web_visit": True,
            "code_interpreter": True,
            "file_search": True,
            "generate_image": True,
        }
        tools = {**default_tools, **(chat_request.tools or {})}

        media_context = None
        if chat_request.media_preferences and chat_request.media_preferences.enabled:
            media_context = await MediaOrchestrator.prepare_media_context(
                db_session=db,
                session_id=session_id,
                media_preferences=chat_request.media_preferences,
                chat_request=chat_request,
                container=self._container,
            )
            tools[media_context.tool_name] = True
            logger.info(
                f"[MEDIA] Prepared media context: tool={media_context.tool_name}"
            )

        model_id = chat_request.model_id

        if media_context and media_context.should_clear_context:
            messages = []
            logger.info(
                f"Media generation (clear context) for session {session_id}"
            )
        else:
            messages = await ContextWindowManager.load_context_for_llm(
                db_session=db,
                session_id=session_id,
            )
            logger.info(
                f"Loaded full context for session {session_id} ({len(messages)} messages)"
            )

        # Build user message content
        display_content = chat_request.content
        llm_content = chat_request.content

        if chat_request.github_repository:
            repo_context = (
                f"\n\n[The user has selected GitHub repository: {chat_request.github_repository.full_name} "
                f"(default branch: {chat_request.github_repository.default_branch}). "
                f"When the user says 'this repository', 'the repository', 'the repo', or similar, "
                f"they are referring to this GitHub repository. Use the github tool to access it.]"
            )
            llm_content += repo_context

        message_metadata = None
        if media_context:
            message_metadata = {
                "media": chat_request.media_preferences.model_dump(
                    exclude_none=True
                )
            }
            llm_content += media_context.tool_hint

        display_text_part = TextContent(text=display_content)
        user_message = await self._message_service.create_message(
            db,
            session_id=str(chat_request.session_id),
            role=MessageRole.USER,
            parts=[display_text_part],
            model_id=chat_request.model_id,
            file_ids=chat_request.file_ids,
            tools=tools,
            metadata=message_metadata,
        )

        chat_run = await self._chat_run_service.create_run(
            db,
            session_id=uuid.UUID(session_id),
            user_message_id=user_message.id,
            model_id=model_id,
            status=ChatRunStatus.RUNNING,
        )
        await db.commit()

        run_id = str(chat_run.id)
        await cancel.register_run(run_id)
        logger.info(f"Started chat run {run_id} for session {session_id}")

        # Phase 1: Process file uploads
        vector_store = await self._file_processor.process_uploads(
            db,
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            llm_content=llm_content,
            display_content=display_content,
        )

        # Build LLM user message with repo context and media parts
        media_message_parts = media_context.llm_message_parts if media_context else []

        llm_parts = [user_message.parts[0]]
        for part in user_message.parts:
            if isinstance(part, BinaryContent):
                llm_parts.append(part)

        if media_message_parts:
            llm_parts.extend(media_message_parts)

        llm_user_message = Message(
            id=user_message.id,
            role=user_message.role,
            session_id=user_message.session_id,
            parts=llm_parts,
            model=user_message.model,
            provider=user_message.provider,
            created_at=user_message.created_at,
            updated_at=user_message.updated_at,
            file_ids=user_message.file_ids,
            tokens=user_message.tokens,
            tools_enabled=user_message.tools_enabled,
            metadata=user_message.metadata,
            provider_metadata=user_message.provider_metadata,
            finish_reason=user_message.finish_reason,
        )
        messages.append(llm_user_message)

        # Phase 2: Build tool registry
        llm_config = await self.get_llm_config(
            db, model_id=model_id, user_id=user_id
        )
        resolved_model_id = (
            llm_config.setting_id
            or llm_config.application_model_name
            or model_id
            or llm_config.model
        )
        await self._chat_run_service.set_provider(
            db,
            chat_run=chat_run,
            provider=llm_config.api_type.value,
            model_id=resolved_model_id,
        )
        provider = LLMProviderFactory.create_provider(llm_config)
        is_code_interpreter_enabled = bool(tools and tools.get("code_interpreter"))

        tool_registry, tools_to_pass = await self._tool_service.build_tool_registry(
            db,
            user_id=user_id,
            session_id=session_id,
            tools=tools,
            chat_request=chat_request,
            vector_store=vector_store,
            media_context=media_context,
        )

        # Phase 3: Run LLM turn loop
        try:
            assistant_message_id: uuid.UUID | None = None
            finish_reason: str | None = None
            async for event in self._llm_loop.run(
                db,
                messages=messages,
                provider=provider,
                tool_registry=tool_registry,
                tools_to_pass=tools_to_pass,
                is_code_interpreter_enabled=is_code_interpreter_enabled,
                session_id=session_id,
                user_id=user_id,
                model_id=model_id,
                user_message=user_message,
                run_id=run_id,
                llm_config=llm_config,
                chat_request=chat_request,
                tool_service=self._tool_service,
            ):
                if event.get("type") == EventType.COMPLETE.value:
                    message_id = event.get("message_id")
                    finish_reason = event.get("finish_reason")
                    if message_id:
                        assistant_message_id = uuid.UUID(str(message_id))
                yield event

            await db.refresh(chat_run)
            await self._chat_run_service.complete_run(
                db,
                chat_run=chat_run,
                assistant_message_id=assistant_message_id,
                finish_reason=finish_reason,
            )
            await db.commit()

            await cancel.cleanup_run(run_id)
            logger.info(f"Completed chat run {run_id} for session {session_id}")

        except (cancel.RunCancelledException, Exception) as e:
            is_cancelled = isinstance(e, cancel.RunCancelledException)

            if is_cancelled:
                logger.info(f"Chat run {run_id} was cancelled for session {session_id}")
            else:
                logger.error(f"Chat streaming error: {e}", exc_info=True)

            await db.refresh(chat_run)
            await self._chat_run_service.fail_run(
                db,
                chat_run=chat_run,
                status=(
                    ChatRunStatus.ABORTED if is_cancelled else ChatRunStatus.FAILED
                ),
                error_message=None if is_cancelled else str(e),
                error_code=self._chat_run_error_code(e, is_cancelled=is_cancelled),
            )
            await db.commit()

            await self._message_service.mark_messages_incomplete(
                db,
                parent_message_id=user_message.id,
            )
            await cancel.cleanup_run(run_id)

            error_text = str(e).lower()
            if isinstance(e, AnthropicImageTooLargeError) or "image exceeds 5 mb" in error_text:
                yield {
                    "type": EventType.ERROR.value,
                    "message": (
                        "Anthropic models cannot process images larger than 5 MB. "
                        "Please switch to another model or upload a smaller image."
                    ),
                    "code": "anthropic_image_too_large",
                }
                return

            if is_cancelled:
                yield {
                    "type": EventType.COMPLETE,
                    "finish_reason": FinishReason.CANCELED,
                }
            else:
                raise

    async def stream_council_chat_response(
        self, db: AsyncSession, *, chat_request: ChatMessageRequest, user_id: str
    ) -> AsyncIterator[Dict]:
        """Stream council response: run multiple LLMs in parallel, then synthesize.

        Orchestrates: context loading, file processing, parallel model execution, synthesis.
        """
        council_prefs = chat_request.council_preferences
        if not council_prefs or not council_prefs.enabled:
            raise ValueError("Council preferences must be enabled")

        CouncilService.validate_preferences(council_prefs)

        session_id = str(chat_request.session_id)

        # Load context
        messages = await ContextWindowManager.load_context_for_llm(
            db_session=db,
            session_id=session_id,
        )
        logger.info(f"Council: loaded context for session {session_id} ({len(messages)} messages)")

        # Build user message content
        display_content = chat_request.content
        llm_content = chat_request.content

        if chat_request.github_repository:
            repo_context = (
                f"\n\n[The user has selected GitHub repository: {chat_request.github_repository.full_name} "
                f"(default branch: {chat_request.github_repository.default_branch}). "
                f"When the user says 'this repository', 'the repository', 'the repo', or similar, "
                f"they are referring to this GitHub repository. Use the github tool to access it.]"
            )
            llm_content += repo_context

        display_text_part = TextContent(text=display_content)
        user_message = await self._message_service.create_message(
            db,
            session_id=session_id,
            role=MessageRole.USER,
            parts=[display_text_part],
            model_id=chat_request.model_id,
            file_ids=chat_request.file_ids,
        )

        agent_task = await self._chat_run_service.create_run(
            db,
            session_id=uuid.UUID(session_id),
            user_message_id=user_message.id,
            status=ChatRunStatus.RUNNING,
        )
        await db.commit()

        run_id = str(agent_task.id)
        await cancel.register_run(run_id)
        logger.info(f"Started council run {run_id} for session {session_id}")

        # Process file uploads (provider-neutral with api_type=None)
        await self._file_processor.process_uploads(
            db,
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            llm_content=llm_content,
            display_content=display_content,
        )

        # Build LLM messages list
        # After process_uploads, user_message.parts[0] already contains
        # llm_content (with GitHub repo context) + file info text
        llm_parts = [user_message.parts[0]]
        for part in user_message.parts:
            if isinstance(part, BinaryContent):
                llm_parts.append(part)

        llm_user_message = Message(
            id=user_message.id,
            role=user_message.role,
            session_id=user_message.session_id,
            parts=llm_parts,
            model=user_message.model,
            provider=user_message.provider,
            created_at=user_message.created_at,
            updated_at=user_message.updated_at,
            file_ids=user_message.file_ids,
            tokens=user_message.tokens,
            tools_enabled=user_message.tools_enabled,
            metadata=user_message.metadata,
            provider_metadata=user_message.provider_metadata,
            finish_reason=user_message.finish_reason,
        )
        messages.append(llm_user_message)

        # Resolve LLM configs for all council models + synthesis model
        all_model_ids = [m.model_id for m in council_prefs.council_models]
        if council_prefs.synthesis_model_id not in all_model_ids:
            all_model_ids.append(council_prefs.synthesis_model_id)

        llm_configs = {}
        model_names = {}
        all_models = await self._llm_setting_service.get_all_available_models(
            db, user_id=user_id
        )
        failed_models = []
        for mid in all_model_ids:
            try:
                llm_configs[mid] = await self.get_llm_config(
                    db, model_id=mid, user_id=user_id
                )
                model_info = next((m for m in all_models.models if m.id == mid), None)
                model_names[mid] = model_info.model if model_info else mid
            except Exception as e:
                logger.warning(f"Could not resolve config for council model {mid}: {e}")
                failed_models.append(mid)

        # Fail fast: synthesis model config is required
        if council_prefs.synthesis_model_id not in llm_configs:
            agent_task.status = ChatRunStatus.FAILED
            await db.commit()
            await cancel.cleanup_run(run_id)
            raise ValueError(
                f"Synthesis model '{council_prefs.synthesis_model_id}' could not be resolved"
            )

        # Fail fast: need at least 2 council models with valid configs
        valid_council_count = sum(
            1 for m in council_prefs.council_models if m.model_id in llm_configs
        )
        if valid_council_count < MIN_COUNCIL_MODELS:
            agent_task.status = ChatRunStatus.FAILED
            await db.commit()
            await cancel.cleanup_run(run_id)
            raise ValueError(
                f"Only {valid_council_count} council models could be resolved, "
                f"need at least {MIN_COUNCIL_MODELS}"
            )

        council_had_error = False
        member_outputs_for_persist = {}
        synthesis_content = ""
        synthesis_model_id = council_prefs.synthesis_model_id

        try:
            async for event in CouncilService.stream_council_response(
                db=db,
                user_id=user_id,
                messages=messages,
                user_question=display_content,
                council_preferences=council_prefs,
                llm_configs=llm_configs,
                model_names=model_names,
                run_id=run_id,
                session_id=session_id,
                llm_execution_service=self._container.llm_execution_service,
            ):
                event_type = event.get("type")

                if event_type == "council_result":
                    # Internal metadata event - don't yield to frontend
                    member_outputs_for_persist = event.get("member_outputs", {})
                    synthesis_content = event.get("synthesis_content", "")
                    synthesis_model_id = event.get("synthesis_model_id", synthesis_model_id)
                    council_had_error = event.get("had_error", False)
                    continue

                if event_type == "council_synthesis_error":
                    council_had_error = True
                    yield event
                    continue

                yield event

            # Persist assistant message with council parts
            assistant_parts = []
            for mid, content in member_outputs_for_persist.items():
                assistant_parts.append(
                    CouncilMemberOutput(
                        model_id=mid,
                        model_name=model_names.get(mid, mid),
                        content=content,
                        status="completed",
                    )
                )

            if synthesis_content:
                assistant_parts.append(
                    CouncilSynthesis(
                        synthesis_model_id=synthesis_model_id,
                        content=synthesis_content,
                    )
                )

            # Don't persist an empty assistant message on total failure
            if not assistant_parts:
                assistant_parts.append(
                    TextContent(text="[Council execution failed - no model produced output]")
                )
                council_had_error = True

            assistant_message = await self._message_service.create_message(
                db,
                session_id=session_id,
                role=MessageRole.ASSISTANT,
                parts=assistant_parts,
                model_id=chat_request.model_id,
            )

            # Update task status
            await db.refresh(agent_task)
            agent_task.status = ChatRunStatus.FAILED if council_had_error else ChatRunStatus.COMPLETED
            await db.commit()

            await cancel.cleanup_run(run_id)

            # Post-response summarization
            try:
                llm_config = await self.get_llm_config(
                    db, model_id=chat_request.model_id, user_id=user_id
                )
                await ContextWindowManager.check_and_summarize_after_response(
                    db_session=db,
                    session_id=session_id,
                    llm_config=llm_config,
                    user_id=user_id,
                )
            except Exception as e:
                logger.warning(f"Post-council summarization failed: {e}")

            yield {
                "type": "complete",
                "message_id": str(assistant_message.id),
                "finish_reason": FinishReason.END_TURN,
            }

            logger.info(f"Completed council run {run_id} for session {session_id}")

        except (cancel.RunCancelledException, Exception) as e:
            is_cancelled = isinstance(e, cancel.RunCancelledException)

            if is_cancelled:
                logger.info(f"Council run {run_id} was cancelled for session {session_id}")
            else:
                logger.error(f"Council streaming error: {e}", exc_info=True)

            await db.refresh(agent_task)
            agent_task.status = ChatRunStatus.ABORTED if is_cancelled else ChatRunStatus.FAILED
            await db.commit()

            await self._message_service.mark_messages_incomplete(
                db,
                parent_message_id=user_message.id,
            )
            await cancel.cleanup_run(run_id)

            if is_cancelled:
                yield {
                    "type": EventType.COMPLETE,
                    "finish_reason": FinishReason.CANCELED,
                }
            else:
                raise

    async def clear_messages(self, db: AsyncSession, *, session_id: str) -> int:
        return await self._message_history._repo.delete_by_session(db, session_id)

    async def stop_conversation(
        self, db: AsyncSession, *, session_id: str
    ) -> Optional[str]:
        session = await self._session_repo.get_by_id(db, session_id)
        if not session:
            raise SessionNotFoundError("Session not found")

        running_run = await self._chat_run_service.find_running_for_cancel(
            db,
            session_id=uuid.UUID(session_id),
        )

        if running_run:
            run_id = str(running_run.id)
            cancelled = await cancel.cancel_run(run_id)
            if cancelled:
                await db.refresh(running_run)
                if running_run.status == ChatRunStatus.RUNNING:
                    running_run.status = ChatRunStatus.ABORTED
                    logger.info(
                        f"Cancelled running chat run {run_id} for session {session_id}"
                    )
                else:
                    logger.info(
                        f"Chat run {run_id} already finished with status {running_run.status}, skipping abort"
                    )

        last_message = await self._message_history._repo.get_last_by_session(db, session_id)

        return str(last_message.id) if last_message else None
