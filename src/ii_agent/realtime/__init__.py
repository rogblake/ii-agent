"""Realtime package: Socket.IO connection management, session tracking, and event broadcasting.

Extracted from ``server.socket`` as part of ADR-003 (DDD + Event-Driven).

Concrete implementations depend on heavy server infrastructure (Socket.IO,
Redis, JWT handlers). Import them directly from their modules::

    from ii_agent.realtime.manager import SocketIOManager
    from ii_agent.realtime.session_store import create_session_store
    from ii_agent.realtime.broadcaster import SocketIOBroadcaster

Only lightweight abstractions are exported at the package level.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ii_agent.realtime.broadcaster import SocketIOBroadcaster
    from ii_agent.realtime.manager import SocketIOManager
    from ii_agent.realtime.session_store import (
        MemorySessionStore,
        RedisSessionStore,
        SessionStore,
    )

__all__ = [
    "SocketIOManager",
    "SessionStore",
    "MemorySessionStore",
    "RedisSessionStore",
    "SocketIOBroadcaster",
]
