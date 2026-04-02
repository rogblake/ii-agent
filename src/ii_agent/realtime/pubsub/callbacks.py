"""Event callback handlers for the pub/sub system."""

from __future__ import annotations

import abc
import logging
from typing import Any

import socketio

from ii_agent.core.db import get_db_session_local
from ii_agent.realtime.events.app_events import BaseEvent, UserMessageEvent
from ii_agent.realtime.events.models import ApplicationEvent
from ii_agent.realtime.events.repository import EventRepository

logger = logging.getLogger(__name__)


class EventCallbackHandler(abc.ABC):
    """ABC for class-based event handlers.

    Implement ``on_event`` to handle events published through ``AsyncIOPubSub``.
    """

    @abc.abstractmethod
    async def on_event(self, event: Any) -> None:
        pass


class DatabaseCallbackHandler(EventCallbackHandler):
    """Persists non-transient events to ``application_events``."""

    def __init__(self, event_repo: EventRepository) -> None:
        self._repo = event_repo

    async def on_event(self, event: BaseEvent) -> None:
        if isinstance(event, UserMessageEvent):
            return
        if event.transient or not event.session_id:
            return

        try:
            async with get_db_session_local() as db:
                serialized_event = event.model_dump(mode="json", exclude_none=True)
                entity = ApplicationEvent(
                    id=event.id,
                    event_type=event.name,
                    event_group=event.group,
                    session_id=event.session_id,
                    run_id=event.run_id,
                    user_id=event.user_id,
                    content=serialized_event.get("content", {}),
                )
                await self._repo.save(db, entity)
        except Exception:
            logger.exception(
                "Failed to persist event %s.%s for session %s",
                event.group,
                event.name,
                event.session_id,
            )


class SioCallbackHandler(EventCallbackHandler):
    """Emits events to Socket.IO session rooms."""

    SIO_EVENT = "chat_event"

    def __init__(self, sio: socketio.AsyncServer) -> None:
        self.sio = sio

    async def on_event(self, event: BaseEvent) -> None:
        if event.session_id is None:
            return
        if event.internal:
            return
        room = str(event.session_id)
        payload = event.to_socket_payload()
        try:
            await self.sio.emit(self.SIO_EVENT, payload, room=room)
        except Exception:
            logger.exception("Failed to emit %s.%s to room %s", event.group, event.name, room)
