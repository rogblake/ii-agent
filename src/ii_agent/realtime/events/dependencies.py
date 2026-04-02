"""FastAPI dependencies for events domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.realtime.events.repository import EventRepository
from ii_agent.realtime.events.service import EventService


# ==================== Repository Dependencies ====================


def get_event_repository() -> EventRepository:
    """Provide EventRepository instance."""
    return EventRepository()


EventRepositoryDep = Annotated[EventRepository, Depends(get_event_repository)]


# ==================== Service Dependencies ====================


def get_event_service(
    event_repo: EventRepositoryDep,
) -> EventService:
    """Provide EventService instance with explicit repo injection."""
    return EventService(event_repo=event_repo, config=get_settings())


EventServiceDep = Annotated[EventService, Depends(get_event_service)]


__all__ = [
    "get_event_repository",
    "get_event_service",
    "EventRepositoryDep",
    "EventServiceDep",
]
