"""Base class for event subscribers."""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import TYPE_CHECKING

from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.agent.runs.models import RunStatus
from ii_agent.core.db.manager import get_db_session_local

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


logger = logging.getLogger(__name__)


class EventSubscriber(ABC):
    """Subscriber that handles metrics updates for sessions."""

    @abstractmethod
    async def handle_event(self, event: RealtimeEvent) -> None:
        """Handle an event."""
        pass

    async def should_handle(self, event: RealtimeEvent) -> bool:
        if event.run_id is None or EventType.is_allowed_when_aborted(event.type):
            return True

        async with get_db_session_local() as db:
            task_run = await self._get_agent_run_service().get_task_by_id(db, task_id=event.run_id)
        if not task_run:
            raise ValueError(f"Task run not found for id: {event.run_id}")

        return task_run.status == RunStatus.RUNNING

    def _get_agent_run_service(self):
        """Get agent_run_service - subclasses with a container use it, otherwise fallback to global."""
        container = getattr(self, "_container", None)
        if container is not None:
            return container.agent_run_service
        # Fallback for subscribers without a container (e.g., MetricsSubscriber)
        from ii_agent.agent.runs.service import AgentRunService
        from ii_agent.agent.runs.repository import AgentRunTaskRepository
        from ii_agent.core.config.settings import get_settings
        return AgentRunService(config=get_settings(), repo=AgentRunTaskRepository())
