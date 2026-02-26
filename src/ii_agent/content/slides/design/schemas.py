"""Pydantic schemas (DTOs) for the slide design domain."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ii_agent.projects.design.schemas import StyleChange


class SlideSyncChange(BaseModel):
    """A single design change to apply to a slide."""
    design_id: str
    type: str
    property: str
    value: Dict[str, Optional[str]] = Field(default_factory=dict)


class SlideSyncBatchRequest(BaseModel):
    """Request to sync design changes to a single slide."""
    session_id: str
    presentation_name: str
    slide_number: int
    changes: List[SlideSyncChange] = Field(default_factory=list)


class SlideSyncBatchResponse(BaseModel):
    """Response from slide sync batch."""
    success: bool
    processed: int = 0
    failed: int = 0
    errors: List[str] = Field(default_factory=list)


class SlideDeckSyncChange(BaseModel):
    """A single design change to apply to a slide in a deck."""
    slide_number: int
    design_id: str
    type: str
    property: str
    value: Dict[str, Optional[str]] = Field(default_factory=dict)


class SlideDeckSyncBatchRequest(BaseModel):
    """Request to sync design changes across multiple slides."""
    session_id: str
    presentation_name: str
    changes: List[SlideDeckSyncChange] = Field(default_factory=list)


class SlideDeckSyncBatchResponse(BaseModel):
    """Response from slide deck sync batch."""
    success: bool
    processed: int = 0
    failed: int = 0
    errors: List[str] = Field(default_factory=list)


class SlideDeckSyncStateRequest(BaseModel):
    """Request body for syncing persisted slide design-mode changes."""
    session_id: str
    presentation_name: str


class SlideDeckSyncStateResponse(BaseModel):
    """Response for syncing persisted slide design-mode changes."""
    success: bool
    applied: int
    total: int
    remaining: int
    errors: List[str] = Field(default_factory=list)
    summary: str
    remaining_changes: List[StyleChange] = Field(default_factory=list)
    event_id: Optional[str] = None
