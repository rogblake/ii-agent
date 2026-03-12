from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict
import uuid

from sqlalchemy.ext.asyncio.session import AsyncSession

from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.agent.events.stream import EventStream
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.agent.socket.schemas import QueryCommandContent
from ii_agent.agent.runs.models import AgentRunTask
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class UserCommandType(str, Enum):
    INIT_AGENT = "init_agent"
    QUERY = "query"
    PLAN = "plan"
    WORKSPACE_INFO = "workspace_info"
    AWAKE_SANDBOX = "awake_sandbox"
    SANDBOX_STATUS = "sandbox_status"
    PING = "ping"
    CANCEL = "cancel"
    CONTINUE_RUN = "continue_run"
    ENHANCE_PROMPT = "enhance_prompt"
    PUBLISH_PROJECT = "publish"
    PUBLISH_CLOUD_RUN = "publish_cloud_run"
    SAVE_ENV = "save_env"
    START_FORK = "start_fork"
    SUBMIT_TESTFLIGHT = "submit_testflight"
    APPLE_AUTH_LOGIN = "apple_auth_login"
    APPLE_AUTH_2FA = "apple_auth_2fa"
    APPLE_AUTH_SELECT_TEAM = "apple_auth_select_team"
    APPLE_APP_SETUP = "apple_app_setup"
    APPLE_LIST_APPS = "apple_list_apps"
    APPLE_CHECK_AUTH = "apple_check_auth"
    SAVE_EXPO_TOKEN = "save_expo_token"
    DESIGN_SYNC = "design_sync"
    DESIGN_SYNC_STATE = "design_sync_state"
    SLIDE_DECK_SYNC_STATE = "slide_deck_sync_state"
    DESIGN_GET_STATE = "design_get_state"
    DESIGN_SAVE_STATE = "design_save_state"


class CommandHandler(ABC):
    """Base class for command handlers.

    Services are accessed via ``self.container`` (a ServiceContainer instance)
    rather than module-level singletons.
    """

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        self.event_stream = event_stream
        self.container = container

    @abstractmethod
    def get_command_type(self) -> UserCommandType:
        """Return the command type this handler processes."""
        pass

    @abstractmethod
    async def handle(self, content: Dict[str, Any], session_info: SessionInfo) -> None:
        """Handle the command with the given content and session.

        Args:
            content: Command content dictionary
            session: Session information
        """
        pass

    async def send_event(self, event: RealtimeEvent) -> None:
        await self.event_stream.publish(event)

    def get_event_stream(self) -> EventStream:
        return self.event_stream

    async def _send_error_event(
        self,
        session_id: str | uuid.UUID,
        message: str,
        error_type: str = "error",
        run_id: uuid.UUID = None,
    ) -> None:
        """Send error event to the session.

        Args:
            session_id: ID of the session to send the error to
            message: Error message to display
            error_type: Type of error for frontend handling
        """

        session_uuid = (
            uuid.UUID(session_id) if isinstance(session_id, str) else session_id
        )

        await self.send_event(
            RealtimeEvent(
                session_id=session_uuid,
                run_id=run_id,
                type=EventType.ERROR,
                content={
                    "message": message,
                    "error_type": error_type,
                },
            )
        )

    async def _send_event(
        self,
        session_id: str | uuid.UUID,
        message: str,
        event_type: EventType,
        run_id: uuid.UUID = None,
        **kwargs,
    ) -> None:
        """Send success event to the session.

        Args:
            session_id: ID of the session to send the event to
            message: Success message to display
            event_type: Type of event (default: "system")
            **kwargs: Additional content to include in the event
        """
        content = {"message": message}
        content.update(kwargs)

        session_uuid = (
            uuid.UUID(session_id) if isinstance(session_id, str) else session_id
        )

        await self.send_event(
            RealtimeEvent(
                session_id=session_uuid,
                run_id=run_id,
                type=event_type,
                content=content,
            )
        )

    async def validate_and_update_session(
        self,
        session_info: SessionInfo,
        query_command: QueryCommandContent,
        min_credits: float = 1.0,
    ) -> tuple[bool, SessionInfo | None, LLMConfig | None]:
        """Validate session exists, user has credits, update session name.

        Delegates to ``SessionService.validate_and_prepare_session()`` for
        business logic, then emits error events when validation fails.

        Returns:
            Tuple of (is_valid, updated_session_info, llm_config)
        """
        async with get_db_session_local() as db:
            result = await self.container.session_validation_service.validate_and_prepare_session(
                db,
                session_info.id,
                query_text=query_command.text if not session_info.name else None,
                agent_type=query_command.agent_type,
                source=query_command.source,
                model_id=query_command.model_id,
                min_credits=min_credits,
                llm_setting_service=self.container.llm_setting_service,
                current_name=session_info.name,
            )

        if not result.is_valid:
            if result.error_message:
                await self._send_error_event(
                    str(session_info.id),
                    message=result.error_message,
                    error_type=result.error_type or "error",
                )
            return False, result.session_info, None

        return True, result.session_info, result.llm_config

    async def create_user_message_event(
        self,
        session_info: SessionInfo,
        query_command: QueryCommandContent,
        db: AsyncSession,
        build_mode: str | None = None,
    ) -> tuple[RealtimeEvent, Any]:
        """Create and save user message event.

        Returns:
            Tuple of (event, saved_db_event)
        """
        files_metadata = []
        if query_command.files:
            for file_id in query_command.files:
                try:
                    file_data = await self.container.file_service.get_file_by_id(db, file_id)
                    files_metadata.append(
                        {
                            "id": file_id,
                            "file_name": file_data.name,
                            "file_size": file_data.size,
                            "content_type": file_data.content_type,
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to get file metadata for {file_id}: {e}")

        content = {
            "text": query_command.text,
            "files": query_command.files,
            "files_metadata": files_metadata,
        }
        if build_mode:
            content["build_mode"] = build_mode

        event = RealtimeEvent(
            session_id=session_info.id,
            type=EventType.USER_MESSAGE,
            content=content,
        )

        saved_event = await self.container.event_service.save_event(db, session_info.id, event)

        return event, saved_event

    async def check_and_create_task(
        self,
        session_info: SessionInfo,
        db: AsyncSession,
        user_message_id: Any,
    ) -> AgentRunTask | None:
        """Check for running task and create new one if none exists.

        Returns:
            New task if created, None if there's already a running task
        """
        running_task = await self.container.agent_run_service.get_running_task(
            db, session_id=session_info.id
        )

        if running_task:
            logger.info(
                f"Already running task for session {session_info.id}, task: {running_task.id}"
            )
            await self._send_error_event(
                str(session_info.id),
                message="Another operation is already running. Please wait.",
                error_type="concurrent_operation_error",
            )
            return None

        return await self.container.agent_run_service.create_task(
            db,
            session_id=session_info.id,
            user_message_id=user_message_id,
        )
