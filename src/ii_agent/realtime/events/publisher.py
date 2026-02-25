"""Event publishing abstractions for realtime transport."""

from __future__ import annotations

import logging
from typing import Protocol

import socketio
from socketio import AsyncRedisManager

from ii_agent.realtime.events.models import RealtimeEvent

logger = logging.getLogger(__name__)


class EventPublisher(Protocol):
    """Transport interface for publishing realtime events."""

    async def publish(self, event: RealtimeEvent) -> None: ...


class NoopEventPublisher:
    """Publisher that intentionally drops events."""

    async def publish(self, event: RealtimeEvent) -> None:
        return


class SocketIOEventPublisher:
    """Publish events to Socket.IO using session room fan-out."""

    def __init__(
        self,
        *,
        sio: socketio.AsyncServer | None = None,
        redis_manager: AsyncRedisManager | None = None,
        namespace: str = "/",
    ) -> None:
        self._sio = sio
        self._redis_manager = redis_manager
        self._namespace = namespace

    async def publish(self, event: RealtimeEvent) -> None:
        if not event.session_id:
            return

        room = str(event.session_id)
        content_with_session = {
            **(event.content or {}),
            "session_id": str(event.session_id),
        }
        event_data = {
            "type": event.type,
            "content": content_with_session,
            "session_id": str(event.session_id),
            "run_id": str(event.run_id) if event.run_id else None,
            "run_status": event.run_status,
        }

        if self._redis_manager is not None:
            try:
                await self._redis_manager.emit(
                    "chat_event",
                    event_data,
                    room=room,
                    namespace=self._namespace,
                )
                return
            except Exception as exc:
                logger.debug("Failed to emit chat_event via redis manager: %s", exc)

        if self._sio is not None:
            try:
                await self._sio.emit("chat_event", event_data, room=room)
            except Exception as exc:
                logger.debug("Failed to emit chat_event via Socket.IO server: %s", exc)


__all__ = [
    "EventPublisher",
    "NoopEventPublisher",
    "SocketIOEventPublisher",
]
