"""Handler for enhance_prompt command."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Any, Optional

from pydantic import ValidationError

from ii_agent.core.db.manager import get_db_session_local
from ii_agent.core.llm.execution_service import LLMBillingContext
from ii_agent.realtime.events.models import EventType, RealtimeEvent
from ii_agent.realtime.events.stream import EventStream
from ii_agent.settings.llm.store import FileSettingsStore
from ii_agent.realtime.socket.schemas import EnhancePromptContent
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.realtime.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)
from ii_agent.utils.prompt_generator import enhance_user_prompt

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class EnhancePromptHandler(CommandHandler):
    """Handler for enhance_prompt command."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        """Initialize the enhance prompt handler with required dependencies.

        Args:
            event_stream: Event stream for publishing events
            container: Service container for dependency injection
        """
        super().__init__(event_stream=event_stream, container=container)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.ENHANCE_PROMPT

    async def handle(self, content: Dict[str, Any], session_info: SessionInfo) -> None:
        """Handle prompt enhancement request."""
        try:
            enhance_content = EnhancePromptContent(**content)

            user_id: Optional[str] = str(session_info.user_id)
            settings_store = await FileSettingsStore.get_instance(self.container.config, user_id)
            settings = await settings_store.load()

            if not settings:
                raise ValueError("Settings not found for user")

            # TODO: what model should be used for enhancement?
            llm_config = settings.llm_configs.get(enhance_content.model_name)
            if not llm_config:
                raise ValueError(
                    f"LLM config not found for model: {enhance_content.model_name}"
                )

            # Enhance the prompt
            async with get_db_session_local() as db:
                success, message, enhanced_prompt = await enhance_user_prompt(
                    llm_execution_service=self.container.llm_execution_service,
                    llm_config=llm_config,
                    user_input=enhance_content.text,
                    files=enhance_content.files,
                    billing_context=LLMBillingContext(
                        db=db,
                        user_id=user_id,
                        session_id=str(session_info.id),
                        llm_config=llm_config,
                        model_id=llm_config.model,
                    ),
                )

            if success and enhanced_prompt:
                await self.send_event(
                    RealtimeEvent(
                        type=EventType.PROMPT_GENERATED,
                        session_id=session_info.id,
                        content={
                            "result": enhanced_prompt,
                            "original_request": enhance_content.text,
                        },
                    )
                )
            else:
                await self._send_error_event(str(session_info.id), message=message)

        except ValidationError as e:
            await self._send_error_event(
                str(session_info.id),
                message=f"Invalid enhance_prompt content: {str(e)}",
                error_type="validation_error",
            )
