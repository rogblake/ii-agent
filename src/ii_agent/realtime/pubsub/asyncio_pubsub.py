"""In-process asyncio-based pub/sub with a single global queue.

All events flow through one queue. Handlers receive every event and
route by ``event.session_id`` internally.

Handlers can be:
- Plain async callables: ``async def handler(event) -> None``
- Objects with ``on_event``: ``class MyHandler: async def on_event(self, event) -> None``
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine

from ii_agent.realtime.events.app_events import BaseEvent
from ii_agent.realtime.pubsub.callbacks import EventCallbackHandler

logger = logging.getLogger(__name__)

Handler = Callable[[Any], Coroutine[Any, Any, None]] | EventCallbackHandler


class AsyncIOPubSub:
    """Lightweight in-process pub/sub backed by a single asyncio queue."""

    def __init__(self) -> None:
        self._handlers: list[Handler] = []
        self._queue: asyncio.Queue[BaseEvent] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._running = False

    def subscribe(self, handler: Handler) -> None:
        """Register a handler. All handlers receive all events."""
        self._handlers.append(handler)

    async def publish(self, event: BaseEvent) -> None:
        """Enqueue an event. Event MUST have session_id."""
        if event.session_id is None:
            raise ValueError(
                f"Events must have session_id, got None for {event.group}.{event.name}"
            )
        await self._queue.put(event)

    @staticmethod
    async def _invoke(handler: Handler, event: BaseEvent) -> None:
        """Call a handler — supports both callables and EventCallbackHandler."""
        if isinstance(handler, EventCallbackHandler):
            await handler.on_event(event)
        else:
            await handler(event)

    async def _dispatch(self) -> None:
        """Single dispatch loop draining the global queue."""
        while True:
            try:
                event = await self._queue.get()
            except asyncio.CancelledError:
                return

            for handler in self._handlers:
                try:
                    await self._invoke(handler, event)
                except Exception:
                    logger.exception(
                        "Handler %s failed for %s.%s session=%s",
                        getattr(handler, "__name__", type(handler).__name__),
                        event.group,
                        event.name,
                        event.session_id,
                    )

            self._queue.task_done()

    async def start(self) -> None:
        """Start the dispatch task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._dispatch(), name="pubsub:global")

    async def stop(self) -> None:
        """Cancel the dispatch task."""
        self._running = False
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
