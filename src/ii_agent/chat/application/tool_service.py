"""Chat tool service for building tool registries and executing tools."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.integrations.connectors.repository import ConnectorRepository
from ii_agent.integrations.connectors.models import ConnectorType
from ii_agent.agents.tools.clients import _get_client
from ii_agent.chat.tools.base import ToolCallInput
from ii_agent.chat.tools.file_search import FileSearchTool
from ii_agent.chat.tools.github import GitHubTool
from ii_agent.chat.tools.image_search import ImageSearchTool
from ii_agent.chat.tools.web_search import WebSearchTool
from ii_agent.chat.tools.web_visit import WebVisitTool
from ii_agent.chat.types import (
    ErrorTextContent,
    ToolResult,
)
from ii_agent.chat.media.orchestrator import MediaOrchestrator

if TYPE_CHECKING:
    from ii_agent.chat.tools.base import BaseTool
    from ii_agent.chat.api.schemas import ChatMessageRequest
    from ii_agent.core.container import ApplicationContainer

logger = logging.getLogger(__name__)


class ChatToolService:
    """Service for building tool registries and executing tools in chat."""

    def __init__(
        self,
        *,
        connector_repo: ConnectorRepository,
        container: ApplicationContainer,
    ) -> None:
        self._connector_repo = connector_repo
        self._container = container

    async def build_tool_registry(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        tools: Dict[str, bool],
        chat_request: "ChatMessageRequest",
        vector_store: Optional[Any],
        media_context: Optional[Any],
    ) -> tuple[Dict[str, "BaseTool"], List[Dict[str, Any]]]:
        """Build the tool registry and OpenAI-format tool definitions.

        Returns (tool_registry, tools_to_pass) tuple.
        """
        tool_registry: Dict[str, "BaseTool"] = {}
        tools_to_pass: List[Dict[str, Any]] = []

        if not (tools and any(tools.values())):
            return tool_registry, tools_to_pass

        tool_client = _get_client()

        all_search_tools: List[BaseTool] = [
            WebSearchTool(tool_client),
            ImageSearchTool(tool_client),
            WebVisitTool(tool_client),
        ]

        if media_context:
            all_search_tools.extend(media_context.tools)
        elif tools.get("generate_image"):
            default_image_tools = await MediaOrchestrator.prepare_default_media_tools(
                session_id=session_id,
                media_type="image",
                container=self._container,
            )
            all_search_tools.extend(default_image_tools)

        if vector_store:
            all_search_tools.append(
                FileSearchTool(
                    session_id=session_id,
                    user_id=user_id,
                    vector_store_id=vector_store.provider_store_id,
                )
            )

        await self._load_connector_tools(
            db=db,
            user_id=user_id,
            chat_request=chat_request,
            tools=tools,
            all_search_tools=all_search_tools,
        )

        enabled_tools: List[BaseTool] = [
            tool for tool in all_search_tools if tools.get(tool.name, False)
        ]

        if not enabled_tools:
            logger.warning(f"No tools enabled in request: {tools}")
        else:
            logger.info(f"Enabled tools: {[t.name for t in enabled_tools]}")

        tool_registry = {tool.name: tool for tool in enabled_tools}

        for tool in enabled_tools:
            tool_info = tool.info()
            tools_to_pass.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool_info.name,
                        "description": tool_info.description,
                        "parameters": tool_info.parameters,
                    },
                }
            )

        return tool_registry, tools_to_pass

    async def _load_connector_tools(
        self,
        *,
        db: AsyncSession,
        user_id: uuid.UUID,
        chat_request: "ChatMessageRequest",
        tools: Dict[str, bool],
        all_search_tools: List["BaseTool"],
    ) -> None:
        """Load connector-based tools dynamically based on user's connected accounts."""
        connectors = await self._connector_repo.get_by_user(db, user_id)

        for connector in connectors:
            if connector.connector_type == ConnectorType.GITHUB.value:
                tools["github"] = True

                github_token = connector.access_token
                github_metadata = connector.connector_metadata or {}

                default_repo = None
                if chat_request.github_repository:
                    default_repo = {
                        "owner": chat_request.github_repository.owner,
                        "name": chat_request.github_repository.name,
                        "full_name": chat_request.github_repository.full_name,
                        "default_branch": chat_request.github_repository.default_branch,
                    }

                all_search_tools.append(
                    GitHubTool(
                        github_token=github_token,
                        github_metadata=github_metadata,
                        default_repository=default_repo,
                    )
                )
                logger.info(f"Loaded GitHub tool for user {user_id}")

    @staticmethod
    async def execute_tool(
        *,
        tool_call_id: str,
        tool_name: str,
        tool_input: str,
        tool_registry: Dict[str, "BaseTool"],
    ) -> "ToolResult":
        """Execute a search tool using the simple tool interface."""
        try:
            tool = tool_registry.get(tool_name)
            if not tool:
                logger.error(f"Tool '{tool_name}' not found in registry")
                return ToolResult(
                    tool_call_id=tool_call_id,
                    name=tool_name,
                    output=ErrorTextContent(
                        value=f"Unknown tool: {tool_name}",
                    ),
                )

            tool_response = await tool.run(
                ToolCallInput(
                    id=tool_call_id,
                    name=tool_name,
                    input=tool_input,
                )
            )

            return ToolResult(
                tool_call_id=tool_call_id,
                name=tool_name,
                output=tool_response.output,
                cost_usd=tool_response.cost_usd,
            )

        except Exception as e:
            logger.error(f"Tool execution error for '{tool_name}': {e}", exc_info=True)
            return ToolResult(
                tool_call_id=tool_call_id,
                name=tool_name,
                output=ErrorTextContent(
                    value=f"Unexpected error executing tool: {str(e)}",
                ),
            )
