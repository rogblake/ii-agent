"""FastAPI dependencies for events domain."""

from typing import Annotated

from fastapi import Depends, Request

from ii_agent.core.config.settings import get_settings
from ii_agent.core.redis import session_manager
from ii_agent.core.events.publisher import (
    EventPublisher,
    NoopEventPublisher,
    SocketIOEventPublisher,
)
from ii_agent.core.events.repository import EventRepository
from ii_agent.core.events.service import EventService


# ==================== Repository Dependencies ====================


def get_event_repository() -> EventRepository:
    """Provide EventRepository instance."""
    return EventRepository()


EventRepositoryDep = Annotated[EventRepository, Depends(get_event_repository)]


# ==================== Service Dependencies ====================


def get_event_publisher(request: Request) -> EventPublisher:
    """Provide the realtime event publisher for HTTP-triggered workflows."""
    sio = getattr(request.app.state, "sio", None)
    if sio is None:
        return NoopEventPublisher()
    return SocketIOEventPublisher(sio=sio, redis_manager=session_manager)


EventPublisherDep = Annotated[EventPublisher, Depends(get_event_publisher)]


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


def get_event_service(
    event_repo: EventRepositoryDep,
    event_publisher: EventPublisherDep,
) -> EventService:
    """Provide EventService instance with explicit repo injection."""
    return build_event_service(event_repo, publisher=event_publisher)


EventServiceDep = Annotated[EventService, Depends(get_event_service)]


__all__ = [
    "build_event_service",
    "get_event_repository",
    "get_event_publisher",
    "get_event_service",
    "EventPublisherDep",
    "EventRepositoryDep",
    "EventServiceDep",
]
