"""Pydantic schemas (DTOs) for the project design domain."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ElementInfoRequest(BaseModel):
    """Element information for AI/design change requests."""

    designId: str
    tagName: str
    className: Optional[str] = None
    textContent: Optional[str] = None
    computedStyles: Optional[Dict[str, Any]] = None
    xpath: Optional[str] = None


class AIChangeRequest(BaseModel):
    """Request body for AI-assisted design change."""

    session_id: str
    element_info: ElementInfoRequest
    user_request: str


class AIChangeResponse(BaseModel):
    """Response from AI change endpoint."""

    changes: List[Dict[str, str]] = Field(default_factory=list)
    explanation: str


class IframeDocumentSnapshotNode(BaseModel):
    designId: str
    tagName: Optional[str] = None
    className: Optional[str] = None
    id: Optional[str] = None
    textContent: Optional[str] = None
    attributes: Optional[Dict[str, str]] = None
    parentDesignId: Optional[str] = None
    childDesignIds: Optional[List[str]] = None
    html: Optional[str] = None


class IframeDocumentSnapshot(BaseModel):
    version: int = 1
    generatedAt: Optional[int] = None
    url: Optional[str] = None
    title: Optional[str] = None
    nodes: List[IframeDocumentSnapshotNode] = Field(default_factory=list)


class IframeAIPlanRequest(BaseModel):
    """Request body for AI edits that operate on the design-mode iframe copy."""

    session_id: str
    user_request: str
    selected_element: Optional[ElementInfoRequest] = None
    document_snapshot: IframeDocumentSnapshot


class IframeAIPlanResponse(BaseModel):
    """Response containing an ordered plan of DOM edits to apply in the iframe."""

    operations: List[Dict[str, Any]] = Field(default_factory=list)
    explanation: str


class ElementContext(BaseModel):
    """Enhanced element context for better source file matching."""

    designId: str
    slideNumber: Optional[int] = None
    tagName: str
    className: Optional[str] = None
    id: Optional[str] = None
    textContent: Optional[str] = None
    innerHTML: Optional[str] = None
    outerHTML: Optional[str] = None
    contextText: Optional[str] = None
    prevSiblingText: Optional[str] = None
    nextSiblingText: Optional[str] = None
    reactSource: Optional[Dict[str, Any]] = None
    attributes: Optional[Dict[str, str]] = None
    parentChain: Optional[List[Dict[str, str]]] = None
    xpath: Optional[str] = None
    computedStyles: Optional[Dict[str, str]] = None


class StyleChange(BaseModel):
    """A single design change with element context."""

    designId: str
    slideNumber: Optional[int] = None
    type: str
    property: str
    value: Dict[str, Any] = Field(default_factory=dict)
    timestamp: int
    elementContext: Optional[ElementContext] = None
    groupId: Optional[str] = None
    groupLabel: Optional[str] = None


class DesignStateRequest(BaseModel):
    """Request body for persisting design-mode state (pending changes)."""

    session_id: str
    changes: List[StyleChange] = Field(default_factory=list)
    redo_changes: Optional[List[StyleChange]] = None


class DesignStateResponse(BaseModel):
    """Response for persisted design-mode state."""

    session_id: str
    changes: List[StyleChange] = Field(default_factory=list)
    redo_changes: List[StyleChange] = Field(default_factory=list)
    updated_at: Optional[int] = None


class SyncRequest(BaseModel):
    """Request body for syncing design changes to workspace files."""

    session_id: str
    changes: List[StyleChange] = Field(default_factory=list)
    project_info: Optional[Dict[str, Any]] = None


class SyncResponse(BaseModel):
    """Response for sync endpoint."""

    success: bool
    applied: int
    errors: List[str] = Field(default_factory=list)


class SyncStateRequest(BaseModel):
    """Request body for syncing persisted design-mode changes."""

    session_id: str


class SyncStateResponse(BaseModel):
    """Response for syncing persisted design-mode changes."""

    success: bool
    applied: int
    total: int
    remaining: int
    errors: List[str] = Field(default_factory=list)
    summary: str
    remaining_changes: List[StyleChange] = Field(default_factory=list)
    event_id: Optional[str] = None
