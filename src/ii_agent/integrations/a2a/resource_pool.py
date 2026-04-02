"""Shared resource pool helpers for the A2A server implementation."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Optional

# from ii_agent.v1.models.openai import get_client as get_llm_client
from ii_agent.utils.workspace_manager import WorkspaceManager

logger = logging.getLogger("a2a_agent")

__all__ = ["ResourcePool", "resource_pool"]


class ResourcePool:
    """Simple resource pool that manages globally shared LLM and workspace resources."""

    def __init__(self):
        self._llm_client: Optional[Any] = None
        self._workspace_manager: Optional[Any] = None
        self._lock = threading.Lock()

    async def get_llm_client(self, config_key: str, config) -> Any:
        """Get or create the shared LLM client."""
        with self._lock:
            if self._llm_client is None:
                logger.info("Creating new LLM client for config: %s", config_key)
                self._llm_client = get_llm_client(config)
            return self._llm_client

    async def get_workspace_manager(
        self, workspace_root: str, container_workspace: Optional[str] = None
    ) -> Any:
        """Get or create the shared workspace manager."""
        with self._lock:
            if self._workspace_manager is None:
                logger.info("Creating new workspace manager for: %s", workspace_root)
                container_path = (
                    Path(container_workspace)
                    if container_workspace and container_workspace.strip()
                    else None
                )
                self._workspace_manager = WorkspaceManager(
                    Path(workspace_root), container_workspace=container_path
                )
            return self._workspace_manager


resource_pool = ResourcePool()
