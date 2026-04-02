"""In-memory session registry that tracks reusable A2A resources per context."""

from __future__ import annotations

import asyncio
import copy
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from ii_agent.integrations.a2a.constants import DEFAULT_SESSION_TTL_SECONDS
from ii_agent.integrations.a2a.context_adapter import A2ARequestPayload, SandboxPreferences, UserAuth


@dataclass
class SessionRecord:
    """State captured for an A2A context to enable reuse."""

    sandbox_id: Optional[str] = None
    sandbox_user_id: Optional[str] = None
    tool_args: Dict[str, Any] = field(default_factory=dict)
    sandbox_preferences: SandboxPreferences = field(default_factory=SandboxPreferences)
    user: UserAuth = field(default_factory=UserAuth)
    last_used: float = field(default_factory=time.time)


class A2ASessionRegistry:
    """Thread-safe registry guarding reusable A2A session state."""

    def __init__(
        self,
        *,
        ttl_seconds: Optional[float] = DEFAULT_SESSION_TTL_SECONDS,
        time_fn: Optional[Callable[[], float]] = None,
    ):
        self._records: Dict[str, SessionRecord] = {}
        self._lock = asyncio.Lock()
        self._ttl_seconds = ttl_seconds if ttl_seconds and ttl_seconds > 0 else None
        self._time_fn = time_fn or time.time

    async def get(self, context_id: str) -> Optional[SessionRecord]:
        """Return a copy of the stored record for ``context_id`` (if any)."""
        async with self._lock:
            now = self._time_fn()
            self._purge_expired_locked(now)
            record = self._records.get(context_id)
            return copy.deepcopy(record) if record else None

    async def upsert(self, context_id: str, record: SessionRecord) -> None:
        """Insert or replace a record for ``context_id``."""
        async with self._lock:
            now = self._time_fn()
            self._purge_expired_locked(now)
            record_copy = copy.deepcopy(record)
            record_copy.last_used = now
            self._records[context_id] = record_copy

    async def remove(self, context_id: str) -> None:
        """Remove a context entry."""
        async with self._lock:
            now = self._time_fn()
            self._purge_expired_locked(now)
            self._records.pop(context_id, None)

    async def touch(self, context_id: str) -> None:
        """Update ``last_used`` timestamp when the context is accessed."""
        async with self._lock:
            now = self._time_fn()
            self._purge_expired_locked(now)
            if context_id in self._records:
                self._records[context_id].last_used = now

    async def snapshot(self) -> Dict[str, SessionRecord]:
        """Return a shallow copy of the registry for observability/testing."""
        async with self._lock:
            now = self._time_fn()
            self._purge_expired_locked(now)
            return copy.deepcopy(self._records)

    async def update_from_payload(
        self,
        context_id: str,
        sandbox_id: Optional[str],
        sandbox_user_id: Optional[str],
        payload: A2ARequestPayload,
        merged_tool_args: Dict[str, Any],
    ) -> None:
        """Helper to upsert data based on the latest request payload."""
        record = SessionRecord(
            sandbox_id=sandbox_id,
            sandbox_user_id=sandbox_user_id,
            tool_args=copy.deepcopy(merged_tool_args),
            sandbox_preferences=payload.sandbox,
            user=payload.user,
            last_used=self._time_fn(),
        )
        await self.upsert(context_id, record)

    def _purge_expired_locked(self, current_time: float) -> None:
        """Remove entries whose ``last_used`` exceeded the TTL."""

        if self._ttl_seconds is None:
            return

        cutoff = current_time - self._ttl_seconds
        expired = [
            context_id
            for context_id, record in self._records.items()
            if record.last_used < cutoff
        ]
        for context_id in expired:
            self._records.pop(context_id, None)
