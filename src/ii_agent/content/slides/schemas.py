"""Pydantic schemas (DTOs) for slides domain."""

from uuid import UUID

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class SlideContentBase(BaseModel):
    """Base model for slide content."""

    presentation_name: str = Field(..., description="Name of the presentation")
    slide_number: int = Field(..., description="Slide number", ge=1)
    slide_title: Optional[str] = Field(None, description="Title of the slide")
    slide_content: str = Field(..., description="HTML content of the slide")


class SlideContentCreate(SlideContentBase):
    """Model for creating slide content (used internally by database_subscriber)."""

    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Additional metadata"
    )


class SlideContentInfo(SlideContentBase):
    """Model for slide content information (used internally)."""

    id: UUID
    session_id: UUID
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: Optional[datetime] = None


class SlideWriteRequest(BaseModel):
    """Request model for slide write operations."""

    presentation_name: str
    slide_number: int
    content: str
    title: str
    description: Optional[str] = None


class SlideWriteResponse(BaseModel):
    """Response model for slide write operations."""

    success: bool
    presentation_name: str
    slide_number: int
    error: Optional[str] = None
    error_code: Optional[str] = None


class PresentationInfo(BaseModel):
    """Model for presentation information from database."""

    name: str
    slide_count: int
    last_updated: Optional[datetime] = None
    slides: List["SlideContentInfo"] = Field(default_factory=list)


class PresentationListResponse(BaseModel):
    """Response model for list of presentations in session."""

    session_id: UUID
    presentations: List[PresentationInfo]
    total: int
