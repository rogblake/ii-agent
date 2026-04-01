"""Pub/sub singleton.

Usage::

    from ii_agent.realtime.pubsub import get_pubsub, AsyncIOPubSub

    pubsub = get_pubsub()
    pubsub.subscribe(my_handler)
    await pubsub.publish(event)
"""

from ii_agent.realtime.pubsub.asyncio_pubsub import AsyncIOPubSub
from ii_agent.realtime.pubsub.callbacks import EventCallbackHandler

_default_pubsub: AsyncIOPubSub | None = None


def get_pubsub() -> AsyncIOPubSub:
    """Get the pub/sub singleton."""
    global _default_pubsub
    if _default_pubsub is None:
        _default_pubsub = AsyncIOPubSub()
    return _default_pubsub


def reset_pubsub() -> None:
    """Reset the pub/sub singleton without stopping."""
    global _default_pubsub
    _default_pubsub = None


async def shutdown_pubsub() -> None:
    """Stop and reset the pub/sub singleton."""
    global _default_pubsub
    if _default_pubsub is not None:
        await _default_pubsub.stop()
        _default_pubsub = None


def set_pubsub(pubsub: AsyncIOPubSub) -> None:
    """Inject a custom pub/sub instance (for testing)."""
    global _default_pubsub
    _default_pubsub = pubsub


__all__ = [
    "AsyncIOPubSub",
    "EventCallbackHandler",
    "get_pubsub",
    "reset_pubsub",
    "shutdown_pubsub",
    "set_pubsub",
]
