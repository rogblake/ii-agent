"""Pydantic schemas (DTOs) for media domain.

Consolidated from:
- server/media_tools/models.py
- server/media_templates/models.py
- legacy_media/media.py (MediaModelConfig, VideoModelsResponse, ImageModelsResponse)
"""

from typing import List, Literal, Optional
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Media Tools Schemas
# =============================================================================

IMAGE_LIMIT_CONFIG: dict[str, tuple[int, int]] = {
    "Group Photo": (2, 4),
}


def get_image_limits(tool_name: str) -> tuple[int, int]:
    """Get (minImages, maxImages) for a tool by name. Default is (1, 4)."""
    return IMAGE_LIMIT_CONFIG.get(tool_name, (1, 4))


class MediaTool(BaseModel):
    """Mini tool descriptor returned to the frontend."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="Tool identifier (kebab-case)")
    name: str = Field(..., description="Display name")
    preview: Optional[str] = Field(
        None, description="Preview image URL for this tool"
    )
    min_images: int = Field(1, description="Minimum number of images required")
    max_images: int = Field(1, description="Maximum number of images allowed")


# =============================================================================
# Media Templates Schemas
# =============================================================================

class MediaTemplateInfo(BaseModel):
    """Model for media template information."""

    id: str
    name: str = Field(..., description="Name of the template")
    type: str = Field(..., description="Type of media (e.g., image, video)")
    prompt: str = Field(..., description="Prompt template for generating media")
    preview: Optional[str] = Field(None, description="Preview image URL")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MediaTemplateListItem(BaseModel):
    """Model for media template list item."""

    id: str
    name: str
    type: str
    preview: Optional[str] = None
    prompt: Optional[str] = None


class MediaTemplatesListResponse(BaseModel):
    """Response model for paginated media templates."""

    templates: List[MediaTemplateListItem]
    total: int
    page: int = Field(..., ge=0)
    page_size: int = Field(..., ge=1, le=100)
    total_pages: int


# =============================================================================
# Reference Image Schemas
# =============================================================================

class ReferenceImageRequest(BaseModel):
    """Request payload for reference image generation."""

    prompt: str
    type: Literal["subject", "scene", "style"]
    session_id: UUID | None = None
    aspect_ratio: Literal["1:1", "16:9", "9:16", "4:3", "3:4"] = "1:1"
    model_name: str | None = None
    provider: str | None = None


class ReferenceImageResponse(BaseModel):
    """Response payload for reference image generation."""

    success: bool
    url: str | None = None
    file_id: UUID | None = None
    error: str | None = None


# =============================================================================
# Media Model Config Schemas (ported from legacy_media/media.py)
# =============================================================================

class MediaModelConfig(BaseModel):
    """Schema for a single media model configuration."""

    id: str
    label: str
    model_name: str
    provider: Literal["gemini", "vertex", "black-forest", "openai", "custom"]
    type: Literal["image", "video", "storybook", "infographic", "poster"]
    description: str
    default_prompt: str | None = None
    source: Literal["user", "system"] | None = None
    # Image-specific properties
    supported_resolutions: list[str] | None = None
    supported_aspect_ratios: list[str] | None = None
    # Video-specific properties
    supported_durations: list[str] | None = None
    supported_video_resolutions: list[str] | None = None
    supported_video_aspect_ratios: list[str] | None = None
    supports_audio: bool | None = None
    supports_multishot: bool | None = None
    supports_start_frame: bool | None = None
    supports_end_frame: bool | None = None
    icon: str


class VideoModelsResponse(BaseModel):
    """Response schema for video models endpoint."""

    models: list[MediaModelConfig]
    suggestions: list[str]


class ImageModelsResponse(BaseModel):
    """Response schema for image models endpoint."""

    models: list[MediaModelConfig]
    storybook_models: list[MediaModelConfig]
    suggestions: list[str]
    storybook_suggestions: list[str]
