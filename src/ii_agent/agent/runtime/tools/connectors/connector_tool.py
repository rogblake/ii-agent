"""Database-backed connector loader."""

from typing import List, Optional, Dict, Set

from sqlalchemy import select

from ii_agent.core.db.manager import get_db_session_local
from ii_agent.core.config.settings import get_settings
from ii_agent.integrations.connectors.models import Connector, ConnectorTypeEnum
from ii_agent.agent.runtime.tools.base import BaseAgentTool
from ii_agent.agent.runtime.tools.connectors.base import BaseConnectorTool
from ii_agent.agent.runtime.tools.connectors.composio_mcp import load_composio_tools_for_user
from ii_agent.agent.runtime.tools.connectors.custom_mcp import load_custom_mcp_tools_for_user
from ii_agent.agent.runtime.tools.connectors.github import GitHubAgentTool
from ii_agent.core.logger import logger


def _add_tools_without_duplicates(
    tools: List[BaseAgentTool],
    new_tools: List[BaseAgentTool],
    existing_names: Set[str],
) -> None:
    """Add tools to list, skipping duplicates by name.

    Args:
        tools: Target list to add tools to.
        new_tools: New tools to add.
        existing_names: Set of existing tool names (updated in-place).
    """
    for tool in new_tools:
        if tool.name not in existing_names:
            tools.append(tool)
            existing_names.add(tool.name)


class ConnectorTool(BaseConnectorTool):
    """Loads connector-based tools from the database for a user."""

    def __init__(
        self,
        user_id: str,
        default_repository: Optional[Dict[str, str]] = None,
    ):
        self._user_id = user_id
        self._default_repository = default_repository

    async def _load_db_connectors(
        self,
        workspace_path: str,
    ) -> List[BaseAgentTool]:
        """Load connector tools from database records."""
        tools: List[BaseAgentTool] = []

        try:
            async with get_db_session_local() as db:
                result = await db.execute(
                    select(Connector).where(Connector.user_id == self._user_id)
                )
                connectors = result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to fetch connectors for user {self._user_id}: {e}")
            return tools

        for connector in connectors:
            if not connector.access_token:
                logger.warning(
                    f"Connector {connector.id} for user {self._user_id} has no access token; skipping"
                )
                continue

            try:
                if connector.connector_type == ConnectorTypeEnum.GITHUB.value:
                    github_tool = GitHubAgentTool(
                        github_token=connector.access_token,
                        workspace_path=workspace_path,
                        github_metadata=connector.connector_metadata or {},
                        default_repository=self._default_repository,
                    )
                    tools.append(github_tool)
                    logger.info(f"Loaded GitHub connector tool for user {self._user_id}")
            except Exception as e:
                logger.error(f"Failed to create connector tool for {connector.connector_type}: {e}")

        return tools

    async def _load_composio_tools(
        self,
    ) -> List[BaseAgentTool]:
        """Load Composio-based connector tools from database.

        Uses composio_mcp module to:
        1. Query active Composio profiles from database
        2. Get actions from Composio SDK
        3. Convert to MCPTool format for execution
        """
        tools: List[BaseAgentTool] = []

        try:
            logger.info(f"[V1 Connector] Loading Composio tools for user {self._user_id}")

            # Load tools from database via composio_mcp module
            composio_tools = await load_composio_tools_for_user(
                user_id=self._user_id,
                composio_api_key=get_settings().composio_api_key,
            )

            logger.info(f"[V1 Connector] Loaded {len(composio_tools)} Composio tools from database")

            return composio_tools

        except Exception as e:
            logger.opt(exception=True).error(f"Failed to load Composio connector tools: {e}")

        return tools

    async def _load_custom_mcp_tools(self) -> List[BaseAgentTool]:
        """Load non-Composio MCP-based tools from database.

        Uses custom_mcp module to:
        1. Query active custom MCP settings from database
        2. Connect to each MCP server and list tools
        3. Convert to UserMCPTool format for execution
        """
        tools: List[BaseAgentTool] = []

        try:
            logger.info(f"[V1 Connector] Loading custom MCP tools for user {self._user_id}")

            # Load tools from database via custom_mcp module
            custom_mcp_tools = await load_custom_mcp_tools_for_user(
                user_id=self._user_id,
            )

            logger.info(
                f"[V1 Connector] Loaded {len(custom_mcp_tools)} custom MCP tools from database"
            )

            return custom_mcp_tools

        except Exception as e:
            logger.opt(exception=True).error(f"Failed to load custom MCP connector tools: {e}")

        return tools

    async def create_connector_tools(
        self, workspace_path: Optional[str] = None
    ) -> List[BaseAgentTool]:
        """Load connector tools for the configured user.

        Loads tools from multiple sources:
        1. Database connectors (GitHub, etc.)
        2. Composio SDK-based tools
        3. MCP server-based tools

        Args:
            workspace_path: Workspace path in sandbox (e.g. "/workspace").

        Returns:
            List of loaded connector tools.
        """

        tools: List[BaseAgentTool] = []
        existing_names: Set[str] = set()

        # # Load database connectors
        # db_tools = await self._load_db_connectors(workspace_path)
        # _add_tools_without_duplicates(tools, db_tools, existing_names)

        # Load Composio tools
        composio_tools = await self._load_composio_tools()
        _add_tools_without_duplicates(tools, composio_tools, existing_names)
        logger.debug(
            f"[V1 Connector] Loaded {len(composio_tools)} Composio connector tools for {composio_tools}"
        )

        # Load custom MCP tools
        custom_mcp_tools = await self._load_custom_mcp_tools()
        _add_tools_without_duplicates(tools, custom_mcp_tools, existing_names)
        logger.debug(f"[V1 Connector] Loaded {len(custom_mcp_tools)} custom MCP connector tools")

        # Log summary
        if tools:
            logger.info(
                f"[V1 Connector] Created {len(tools)} total connector tools for user {self._user_id}"
            )
            logger.debug(f"[V1 Connector] Final tool list: {[t.name for t in tools]}")
        else:
            logger.warning(f"[V1 Connector] No connector tools available for user {self._user_id}")

        return tools
