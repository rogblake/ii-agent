"""Internal domain models for project design synchronization flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ii_agent.projects.design.schemas import StyleChange


@dataclass(slots=True)
class DesignSyncCounters:
    """Mutable counters used while applying design changes."""

    processed: int = 0
    failed: int = 0
    applied: int = 0
    errors: List[str] = field(default_factory=list)


@dataclass(slots=True)
class PersistedDesignSyncResult:
    """Internal result model for persisted design-mode sync operations."""

    success: bool
    applied: int
    total: int
    remaining_changes: List[StyleChange] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    summary: str = ""
    event_id: str | None = None
