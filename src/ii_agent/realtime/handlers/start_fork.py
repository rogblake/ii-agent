"""Handler for starting forked sessions."""

import uuid
from typing import Any, cast

from ii_agent.agents.types import AgentType
from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.core.container import ApplicationContainer
from ii_agent.core.db import get_db_session_local
from ii_agent.realtime.schemas import StartForkContent, QueryCommandContent
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.realtime.events.app_events import ErrorCode
from ii_agent.realtime.handlers.base import (
    BaseCommandHandler,
    CommandType,
)
from ii_agent.realtime.handlers.query import UserQueryHandler
from ii_agent.agents.prompts.research_to_website_prompt import format_fork_user_message
from ii_agent.core.logger import logger

class StartForkHandler(BaseCommandHandler[StartForkContent]):
    """Handler for starting forked sessions.

    Reads fork_info from session metadata and constructs the appropriate
    prompt based on fork_type, then delegates to the query handler.
    """

    _content_type = StartForkContent

    def __init__(self, pubsub: AsyncIOPubSub, query_handler: UserQueryHandler, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)
        self._query_handler = query_handler

    def get_command_type(self) -> CommandType:
        return CommandType.START_FORK

    async def handle(self, content: StartForkContent, session_info: SessionInfo) -> None:
        """Handle fork session start by reading fork_info and constructing the prompt."""
        fork_content = content

        # Read fork_info from session metadata
        session_id = (
            uuid.UUID(session_info.id) if isinstance(session_info.id, str) else session_info.id
        )
        fork_info = await self._get_fork_info(session_id)

        if not fork_info:
            await self._send_error_event(
                session_info.id,
                error_code=ErrorCode.INVALID_FORK_SESSION,
            )
            return

        # Construct the prompt based on fork_type
        prompt_text = self._build_fork_prompt(fork_info)

        if not prompt_text:
            await self._send_error_event(
                session_info.id,
                error_code=ErrorCode.UNKNOWN_FORK_TYPE,
                message=f"Unknown fork type: {fork_info.get('fork_type')}",
            )
            return

        # Determine agent type from fork_type or content
        agent_type = self._determine_agent_type(fork_info, fork_content)

        # Build QueryCommandContent and delegate to query handler
        query_content = QueryCommandContent(
            model_id=fork_content.model_id,
            provider=None,
            source=fork_content.source,
            agent_type=agent_type,
            tool_args=fork_content.tool_args,
            thinking_tokens=fork_content.thinking_tokens,
            metadata=fork_content.metadata,
            text=prompt_text,
            resume=False,
            files=[],  # Fork attachments are referenced by path, not file IDs
            build_mode="build",
        )

        # Delegate to query handler
        await self._query_handler.dispatch(query_content.model_dump(), session_info)

    async def _get_fork_info(self, session_id: uuid.UUID) -> dict[str, Any] | None:
        """Read fork_info from session metadata.

        Args:
            session_id: Session UUID to look up

        Returns:
            fork_info dict or None if not found
        """
        container = self._container
        async with get_db_session_local() as db:
            session = await container.session_service.get_session_by_id(db, session_id)
            if not session or not session.session_metadata:
                return None

            return cast(dict[str, Any] | None, session.session_metadata.get("fork_info"))

    def _build_fork_prompt(self, fork_info: dict[str, Any]) -> str | None:
        """Build the prompt text based on fork_type.

        Args:
            fork_info: Fork information from session metadata

        Returns:
            Constructed prompt text or None if fork_type is unknown
        """
        fork_type = fork_info.get("fork_type")
        context = fork_info.get("context", {})
        attachments = context.get("attachments", [])
        additional_instruction = context.get("additional_instruction")

        if fork_type == "research_to_website":
            # Determine research mode from parent agent type
            parent_agent_type = fork_info.get("parent_agent_type", "") or ""
            if "deep" in parent_agent_type.lower():
                research_mode = "deep"
            elif "fast" in parent_agent_type.lower():
                research_mode = "fast"
            else:
                research_mode = "unknown"

            # Use the existing prompt function
            return format_fork_user_message(
                attachments=attachments,
                research_mode=research_mode,
                additional_instruction=additional_instruction,
            )
        elif fork_type == "research_to_slide":
            # TODO: Create a separate prompt file for slides when needed
            return self._build_research_to_slide_prompt(attachments, additional_instruction)
        else:
            logger.warning(f"Unknown fork_type: {fork_type}")
            return None

    def _build_research_to_slide_prompt(
        self,
        attachments: list[str],
        additional_instruction: str | None,
    ) -> str:
        """Build prompt for research_to_slide fork type.

        TODO: Move to a separate prompt file when slide agent is fully implemented.
        """
        attachments_list = "\n".join(f"- {file}" for file in attachments)

        prompt = f"""Build a presentation/slides based on the research output files.

<attachments>
{attachments_list}
</attachments>
"""

        if additional_instruction:
            prompt += f"""
<additional_instruction>
This is the instruction from user. If any conflict with above, prefer this one:
{additional_instruction}
</additional_instruction>
"""

        prompt += """
Please read the research files first to understand the content, then create a plan and build the presentation.
"""

        return prompt

    def _determine_agent_type(
        self,
        fork_info: dict[str, Any],
        fork_content: StartForkContent,
    ) -> AgentType:
        """Determine the agent type based on fork_type or explicit content.

        Args:
            fork_info: Fork information from session metadata
            fork_content: Content from frontend request

        Returns:
            AgentType for the forked session
        """
        # If frontend explicitly specifies agent_type, use it
        if fork_content.agent_type:
            try:
                return AgentType(fork_content.agent_type)
            except ValueError:
                pass

        # Otherwise, derive from fork_type
        fork_type = fork_info.get("fork_type")

        if fork_type == "research_to_website":
            return AgentType.RESEARCH_TO_WEBSITE
        elif fork_type == "research_to_slide":
            return AgentType.SLIDE
        else:
            return AgentType.GENERAL
