"""Abstract base class for connector-based tool creation."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from ii_agent.utils.workspace_manager import WorkspaceManager
    from ii_agent.engine.v1.tools.base import BaseAgentTool


class BaseConnectorTool(ABC):
    """Interface for creating connector-backed tools (e.g., GitHub)."""

    @abstractmethod
    async def create_connector_tools(
        self, workspace_manager: Optional["WorkspaceManager"] = None
    ) -> List["BaseAgentTool"]:
        """Create connector tools for the current user/context.

        Args:
            workspace_manager: Workspace manager for file operations where needed.

        Returns:
            List of connector tools (empty if none available or loading fails).
        """
        raise NotImplementedError
