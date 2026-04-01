"""Utility to load connector-based tools for agent system."""

import logging
from typing import List, Optional, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.integrations.connectors.models import Connector, ConnectorType
from ii_agent.agents.tools.base import BaseAgentTool
from ii_agent.agents.tools.connectors.github import GitHubAgentTool

logger = logging.getLogger(__name__)


async def load_connector_tools(
    db_session: AsyncSession,
    user_id: str,
    workspace_path: str,
    sandbox: Any,
    default_repository: Optional[dict] = None,
) -> List[BaseAgentTool]:
    """Load connector-based tools for a user.

    This function queries the database for the user's connected services
    and instantiates the appropriate tool classes. This makes it easy to
    add new connector-based tools in the future.

    Args:
        db_session: Database session
        user_id: User ID to load connectors for
        workspace_path: Workspace path in sandbox (e.g. "/workspace")
        sandbox: Sandbox instance for running commands
        default_repository: Optional default GitHub repository context
            Format: {"owner": "...", "name": "...", "full_name": "...", "default_branch": "..."}

    Returns:
        List[BaseAgentTool]: List of connector tool instances

    Example:
        tools = await load_connector_tools(db, user_id, workspace_path, sandbox, {"owner": "acme", "name": "repo"})
        # Returns [GitHubAgentTool(...)] if user has GitHub connected
    """
    connector_tools: List[BaseAgentTool] = []

    # Query all connectors for the user
    result = await db_session.execute(
        select(Connector).where(Connector.user_id == user_id)
    )
    connectors = result.scalars().all()

    # Process each connector and instantiate appropriate tools
    for connector in connectors:
        try:
            if connector.connector_type == ConnectorType.GITHUB.value:
                # Enable GitHub tool
                github_token = connector.access_token
                github_metadata = connector.connector_metadata or {}

                # Instantiate GitHub tool
                github_tool = GitHubAgentTool(
                    github_token=github_token,
                    workspace_path=workspace_path,
                    github_metadata=github_metadata,
                    default_repository=default_repository,
                )
                connector_tools.append(github_tool)
                logger.info(f"Loaded GitHub tool for user {user_id}")

        except Exception as e:
            logger.error(
                f"Failed to load connector tool for {connector.connector_type}: {e}"
            )
            # Continue loading other connectors even if one fails
            continue

    if connector_tools:
        logger.info(
            f"Loaded {len(connector_tools)} connector tools for user {user_id}: "
            f"{[tool.name for tool in connector_tools]}"
        )
    else:
        logger.debug(f"No connector tools available for user {user_id}")

    return connector_tools
