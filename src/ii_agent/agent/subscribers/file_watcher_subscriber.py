"""Subscriber that starts a file watcher on the first tool result for a session."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.agent.subscribers.subscriber import EventSubscriber

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class FileWatcherSubscriber(EventSubscriber):
    """Trigger ``ensure_watching`` on every TOOL_RESULT event.

    ``ensure_watching`` is idempotent -- after the first call starts the
    watcher, subsequent calls are a cheap dict-lookup + set-add no-op.
    """

    def __init__(self, container: ServiceContainer) -> None:
        super().__init__()
        self._container = container

    async def handle_event(self, event: RealtimeEvent) -> None:
        if event.type != EventType.TOOL_RESULT:
            return
        if event.session_id is None:
            return
        await self._container.workspace_explorer_service.ensure_watching_by_session_id(
            session_id=event.session_id
        )
