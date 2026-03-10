"""Typed dependency container for V1 tools.

Provides tool instances with their external client dependencies
via constructor injection instead of module-level globals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ii_agent.core.container import ServiceContainer
from ii_agent.engine.runtime.tools.clients import _get_client

if TYPE_CHECKING:
    from ii_agent.realtime.events.service import EventService
    from ii_agent.projects.service import ProjectService
    from ii_agent.sessions.service import SessionService
    from ii_agent.engine.runtime.tools.clients import IIToolClient


@dataclass
class ToolDependencies:
    """Dependencies available to all V1 agent tools.

    Created once per agent run and set on tool instances via
    ``BaseAgentTool.dependencies``.
    """

    tool_client: IIToolClient
    container: ServiceContainer

    @property
    def session_service(self) -> SessionService:
        return self.container.session_service

    @property
    def event_service(self) -> EventService:
        return self.container.event_service

    @property
    def project_service(self) -> ProjectService:
        return self.container.project_service

    @classmethod
    def create_default(cls) -> ToolDependencies:
        """Create with the default (lazy-singleton) tool client."""

        return cls(
            tool_client=_get_client(),
            container=ServiceContainer.create(),
        )
