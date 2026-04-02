"""Storybook Pydantic models for API request/response validation."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StorybookPageBase(BaseModel):
    """Base model for storybook page data."""

    page_number: int = Field(..., description="Page number (1-indexed)", ge=1)
    image_url: Optional[str] = Field(None, description="URL to the generated image")
    image_prompt: Optional[str] = Field(None, description="Prompt used to generate the image")
    text_content: Optional[str] = Field(None, description="Narrative text content")
    text_position: str = Field("none", description="Position of text (left/right/top/bottom/none)")
    text_percentage: int = Field(
        30, description="Percentage of page for text (20-30)", ge=0, le=100
    )


class StorybookPageCreate(StorybookPageBase):
    """Model for creating a storybook page."""

    audio_link: Optional[str] = Field(None, description="Public URL to generated audio narration")
    html_content: Optional[str] = Field(None, description="Pre-generated HTML for rendering")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Additional metadata"
    )


class StorybookPageInfo(StorybookPageBase):
    """Model for storybook page information."""

    id: UUID
    storybook_id: UUID
    html_content: Optional[str] = None
    audio_link: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class StorybookBase(BaseModel):
    """Base model for storybook data."""

    name: str = Field(..., description="Name/title of the storybook")
    aspect_ratio: str = Field("1:1", description="Aspect ratio (e.g., 1:1)")
    resolution: str = Field("1K", description="Resolution (e.g., 1K)")


class StorybookCreate(StorybookBase):
    """Model for creating a storybook."""

    style_json: Optional[Dict[str, Any]] = Field(
        None,
        description="Style parameters (character_description, art_style, color_palette)",
    )


class StorybookInfo(StorybookBase):
    """Model for storybook information (without pages)."""

    id: UUID
    session_id: UUID
    version: int = 1
    root_storybook_id: Optional[UUID] = None
    parent_storybook_id: Optional[UUID] = None
    style_json: Optional[Dict[str, Any]] = None
    page_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class StorybookDetail(StorybookInfo):
    """Model for storybook with all pages."""

    pages: List[StorybookPageInfo] = Field(default_factory=list)


class PageTextUpdateRequest(BaseModel):
    """Request model for updating page text only."""

    text_content: str = Field(..., description="New text content for the page")


class PageRegenerateRequest(BaseModel):
    """Request model for regenerating page image."""

    image_prompt: str = Field(..., description="New or same prompt for image generation")


class StorybookListResponse(BaseModel):
    """Response model for list of storybooks."""

    session_id: UUID
    storybooks: List[StorybookInfo]
    total: int


# ============================================================================
# Generation Progress / Result Models
# ============================================================================


class StorybookProgressPage(BaseModel):
    """Progress page info for storybook generation."""

    page_number: int
    image_url: Optional[str] = None


class StorybookProgressResponse(BaseModel):
    """Progress response for storybook generation."""

    type: Literal["storybook_progress"] = "storybook_progress"
    storybook_id: UUID
    storybook_name: str
    total_pages: int
    completed_pages: int
    current_page: int
    status: Literal["generating", "completed", "failed"] = "generating"
    pages: List[StorybookProgressPage] = Field(default_factory=list)
    page: Optional[StorybookProgressPage] = None
    error_message: Optional[str] = None
    generating_pages: List[int] = Field(default_factory=list)


class StorybookResultPage(BaseModel):
    """Result page info for completed storybook generation."""

    page_number: int
    image_url: str
    text_content: Optional[str] = None
    audio_link: Optional[str] = None
    text_position: str = "none"
    text_percentage: int = 30


class StorybookResultResponse(BaseModel):
    """Result response for completed storybook generation."""

    type: Literal["storybook"] = "storybook"
    storybook_id: UUID
    storybook_name: str
    version: int = 1
    pages: List[StorybookResultPage] = Field(default_factory=list)
    aspect_ratio: str = "1:1"
    resolution: str = "1K"


StorybookGenerationResponse = Union[StorybookProgressResponse, StorybookResultResponse]


class StorybookVersionResponse(BaseModel):
    """Response model for creating a new storybook version."""

    success: bool
    storybook: Optional[StorybookDetail] = None
    error: Optional[str] = None


class StorybookVoiceOverResponse(BaseModel):
    """Response model for generating storybook voice-over."""

    success: bool
    storybook: Optional[StorybookDetail] = None
    error: Optional[str] = None


# ============================================================================
# Storybook Edit Mode Models
# ============================================================================


class DesignChange(BaseModel):
    """Design change tracking model for storybook editing."""

    designId: str = Field(..., description="Element's data-design-id attribute")
    type: str = Field(..., description="Change type: 'style', 'text', 'attribute', or 'move'")
    property: str = Field(..., description="CSS property, 'textContent', 'icon', etc.")
    value: Dict[str, Optional[str]] = Field(
        ..., description="Change value with 'from' and 'to' keys"
    )
    timestamp: int = Field(..., description="Unix timestamp when change was made")
    elementContext: Optional[Dict[str, Any]] = Field(
        None, description="Full element snapshot for context"
    )
    groupId: Optional[str] = Field(None, description="Group ID for multi-step operations")
    groupLabel: Optional[str] = Field(None, description="Human-readable group label")


class PageChanges(BaseModel):
    """Changes for a single page in a storybook."""

    page_number: int = Field(..., description="Page number (1-indexed)", ge=1)
    changes: List[DesignChange] = Field(
        default_factory=list, description="List of design changes for this page"
    )
    image_url: Optional[str] = Field(
        None, description="New image URL if the page image was regenerated"
    )


class SaveEditsRequest(BaseModel):
    """Request model for saving storybook edits."""

    storybook_id: UUID = Field(..., description="ID of the storybook being edited")
    page_changes: List[PageChanges] = Field(..., description="Changes for each modified page")


class SaveEditsResponse(BaseModel):
    """Response model for saving storybook edits."""

    success: bool
    storybook: Optional[StorybookDetail] = None
    error: Optional[str] = None


class VersionInfo(BaseModel):
    """Version information for a storybook."""

    id: UUID = Field(..., description="Storybook ID for this version")
    version: int = Field(..., description="Version number")
    created_at: Optional[datetime] = Field(None, description="When this version was created")
    is_current: bool = Field(..., description="Whether this is the current/latest version")


class VersionHistoryResponse(BaseModel):
    """Response model for version history."""

    versions: List[VersionInfo] = Field(
        default_factory=list, description="List of versions, newest first"
    )


# ============================================================================
# Storybook Upload Models
# ============================================================================


class StorybookBackgroundUploadResponse(BaseModel):
    """Response model for storybook background/reference image upload."""

    url: str = Field(..., description="Public URL of uploaded image")
    storage_path: str = Field(..., description="Storage path of uploaded image")


# ============================================================================
# AI Feature Models
# ============================================================================


class AIRewriteRequest(BaseModel):
    """Request model for AI text rewrite."""

    storybook_id: UUID = Field(..., description="ID of the storybook being edited")
    content: str = Field(..., description="Current text content to rewrite")
    page_image_url: Optional[str] = Field(
        None, description="URL of the current page image for context"
    )
    element_context: Optional[Dict[str, Any]] = Field(
        None, description="Context about the element being edited"
    )


class AIRewriteResponse(BaseModel):
    """Response model for AI text rewrite."""

    success: bool
    rewritten_content: Optional[str] = None
    error: Optional[str] = None


class AIGenerateBackgroundRequest(BaseModel):
    """Request model for AI background image generation."""

    storybook_id: UUID = Field(..., description="ID of the storybook being edited")
    prompt: str = Field(..., description="Text prompt describing the background to generate")
    page_image_url: Optional[str] = Field(
        None, description="URL of the current page image for extending"
    )
    text_position: Optional[str] = Field(
        None,
        description="Text position to determine extension direction: left, right, top, bottom, separate_page",
    )


class AIGenerateBackgroundResponse(BaseModel):
    """Response model for AI background image generation."""

    success: bool
    image_url: Optional[str] = None
    error: Optional[str] = None


class AIRegenerateImageRequest(BaseModel):
    """Request model for AI image regeneration."""

    storybook_id: UUID = Field(..., description="ID of the storybook being edited")
    page_number: int = Field(..., description="Page number to regenerate", ge=1)
    prompt: str = Field(..., description="User prompt describing the update")
    reference_image_url: Optional[str] = Field(
        None, description="Reference image URL for style guidance"
    )
    scene_text: Optional[str] = Field(None, description="Scene text to include for context")
    text_position: Optional[str] = Field(
        None,
        description="Text position for layout context: left, right, top, bottom, separate_page, none",
    )
    text_percentage: Optional[int] = Field(None, description="Text percentage for layout context")


class AIRegenerateImageResponse(BaseModel):
    """Response model for AI image regeneration."""

    success: bool
    image_url: Optional[str] = None
    error: Optional[str] = None
