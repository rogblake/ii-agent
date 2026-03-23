from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from ii_agent.agent.events.models import RealtimeEvent, EventType
from ii_agent.agent.events.repository import EventRepository
from ii_agent.agent.subscribers.subscriber import EventSubscriber
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class DatabaseSubscriber(EventSubscriber):
    """Subscriber that handles database storage for events."""

    def __init__(self, container: ServiceContainer) -> None:
        super().__init__()
        self._container = container

    async def handle_event(self, event: RealtimeEvent) -> None:
        """Handle an event by saving it to the database."""
        # Save all events to database if we have a session
        if not await self.should_handle(event):
            return

        if event.type == EventType.USER_MESSAGE:
            # Skip saving user message events to avoid duplication
            return

        if event.type == EventType.PLAN_GENERATED:
            # Skip - these are manually saved in query_handler.py
            return

        if event.type == EventType.MILESTONE_UPDATE:
            # Skip - these are manually saved in query_handler.py
            return

        if event.type in (EventType.AGENT_THINKING_DELTA, EventType.AGENT_RESPONSE_DELTA):
            # Skip streaming delta events - final content saved via completed events
            return

        if not event.session_id:
            return

        # Handle file URLs from image/video generation tools
        if event.type == EventType.TOOL_RESULT:
            tool_result = event.content.get("result", {})
            tool_name = event.content.get("tool_name", "")

            # Special handling for file_url type results (image/video generation)
            if isinstance(tool_result, dict) and tool_result.get("type") == "file_url":
                try:
                    async with get_db_session_local() as db:
                        file_data = await self._container.file_service.write_file_from_url(
                            db=db,
                            url=tool_result["url"],
                            file_name=tool_result["name"],
                            file_size=tool_result["size"],
                            content_type=tool_result["mime_type"],
                            session_id=str(event.session_id),
                        )
                    event.content["result"]["file_id"] = file_data.id
                    event.content["result"]["file_storage_path"] = file_data.storage_path
                except Exception:
                    logger.exception(
                        "Failed to persist tool result file for session {} and tool {}",
                        event.session_id,
                        tool_name or "<unknown>",
                    )

            # All tool results (including non-file results) are saved with the event
        try:
            async with get_db_session_local() as db:
                event_repo = EventRepository()
                await event_repo.save(db, event.session_id, event)
        except IntegrityError:
            # Event already saved elsewhere (e.g., manually in query_handler.py), ignore
            pass
