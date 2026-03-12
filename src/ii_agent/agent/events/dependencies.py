"""FastAPI dependencies for events domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.agent.events.publisher import EventPublisher
from ii_agent.agent.events.repository import EventRepository
from ii_agent.agent.events.service import EventService


# ==================== Repository Dependencies ====================


def get_event_repository() -> EventRepository:
    """Provide EventRepository instance."""
    return EventRepository()


EventRepositoryDep = Annotated[EventRepository, Depends(get_event_repository)]


# ==================== Service Dependencies ====================


def build_event_service(
    event_repo: EventRepository,
    *,
    publisher: EventPublisher | None = None,
) -> EventService:
    """Create EventService with optional transport publisher."""
    return EventService(
        event_repo=event_repo,
        config=get_settings(),
        publisher=publisher,
    )


__all__ = [
    "build_event_service",
    "get_event_repository",
    "EventRepositoryDep",
]
