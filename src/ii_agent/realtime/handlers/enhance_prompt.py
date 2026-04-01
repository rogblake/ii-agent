"""Handler for enhance_prompt command.

Extracted from ``server.socket.command.enhance_prompt_handler``.
"""

from ii_agent.core.container import ApplicationContainer
from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.realtime.events.app_events import AgentPromptGeneratedEvent, ErrorCode
from ii_agent.core.config.settings import get_settings
from ii_agent.core.logger import logger
from ii_agent.integrations.enhance_prompt.client import create_enhance_prompt_client
from ii_agent.realtime.schemas import EnhancePromptContent
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.realtime.handlers.base import (
    BaseCommandHandler,
    CommandType,
)


class EnhancePromptHandler(BaseCommandHandler[EnhancePromptContent]):
    """Handler for enhance_prompt command."""

    _content_type = EnhancePromptContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)

    def get_command_type(self) -> CommandType:
        return CommandType.ENHANCE_PROMPT

    async def handle(self, content: EnhancePromptContent, session_info: SessionInfo) -> None:
        """Handle prompt enhancement request."""
        try:
            cfg = get_settings()
            client = create_enhance_prompt_client(cfg.enhance_prompt)
            if client is None:
                await self.send_event(
                    AgentPromptGeneratedEvent(
                        session_id=session_info.id,
                        prompt=content.text,
                        content={
                            "result": content.text,
                            "original_request": content.text,
                        },
                    )
                )
                return

            result = await client.enhance(content.text)

            await self.send_event(
                AgentPromptGeneratedEvent(
                    session_id=session_info.id,
                    prompt=result.enhanced_prompt,
                    content={
                        "result": result.enhanced_prompt,
                        "original_request": content.text,
                    },
                )
            )

        except Exception as e:
            logger.error(f"Error enhancing prompt: {e}", exc_info=True)
            await self._send_error_event(
                session_info.id,
                error_code=ErrorCode.ENHANCE_PROMPT_ERROR,
            )
