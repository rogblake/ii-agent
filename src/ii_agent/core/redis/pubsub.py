"""Generic pub/sub service for distributed messaging.

Import pattern:
    from ii_agent.core.redis import AsyncIOPubSub
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine, Dict, List

logger = logging.getLogger(__name__)


class AsyncIOPubSub:
    """In-memory async pub/sub implementation using asyncio queues.

    WARNING: Only works within a single process/worker.
    For multi-worker deployments, use Redis pub/sub directly.
    """

    def __init__(self):
        self.subscribers: Dict[str, List[Callable[[Any], Coroutine]]] = defaultdict(list)
        self.queues: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self.tasks: List[asyncio.Task] = []

    def subscribe(self, topic: str, handler: Callable[[Any], Coroutine]):
        """Subscribe a handler to a topic."""
        self.subscribers[topic].append(handler)

    async def publish(self, topic: str, message: Any):
        """Publish a message to a topic."""
        await self.queues[topic].put(message)

    async def _dispatch(self, topic: str):
        """Dispatch messages to subscribers for a topic."""
        while True:
            msg = await self.queues[topic].get()
            handlers = self.subscribers.get(topic, [])
            for handler in handlers:
                asyncio.create_task(handler(msg))

    async def start(self):
        """Start the pub/sub dispatcher tasks."""
        for topic in self.subscribers:
            self.tasks.append(asyncio.create_task(self._dispatch(topic)))

    async def stop(self):
        """Stop all dispatcher tasks."""
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)


__all__ = ["AsyncIOPubSub"]
