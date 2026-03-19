"""Abstract base class for connector-based tool creation."""

from abc import ABC, abstractmethod
from typing import List, Optional

from ii_agent.agent.runtime.tools.base import BaseAgentTool


class BaseConnectorTool(ABC):
    """Interface for creating connector-backed tools (e.g., GitHub)."""

    @abstractmethod
    async def create_connector_tools(
        self, workspace_path: Optional[str] = None
    ) -> List[BaseAgentTool]:
        """Create connector tools for the current user/context.

        Args:
            workspace_path: Workspace path in sandbox (e.g. "/workspace").

        Returns:
            List of connector tools (empty if none available or loading fails).
        """
        raise NotImplementedError
