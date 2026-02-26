"""Pydantic schemas (DTOs) for Nano Banana design mode endpoints."""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ============ Enums ============


class SelectionType(str, Enum):
    """Type of user selection on the slide."""

    COMPONENT = "component"  # Selected a detected component
    SPOT = "spot"  # Clicked a single point
    BOX = "box"  # Dragged a rectangular region


class InstructionType(str, Enum):
    """Type of edit instruction."""

    TEXT_EDIT = "text_edit"
    AI_MODIFY = "ai_modify"
    REMOVE_BACKGROUND = "remove_background"


# ============ Detection Models ============


class BoundingBox(BaseModel):
    """Percentage-based bounding box relative to image dimensions (0-100)."""

    x: float = Field(..., ge=0, le=100, description="Left edge as % of image width")
    y: float = Field(..., ge=0, le=100, description="Top edge as % of image height")
    width: float = Field(..., gt=0, le=100, description="Width as % of image width")
    height: float = Field(..., gt=0, le=100, description="Height as % of image height")


class ComponentStyles(BaseModel):
    """Detected visual properties of a component."""

    font_size: Optional[str] = None
    font_weight: Optional[str] = None
    color: Optional[str] = None
    background_color: Optional[str] = None
    text_align: Optional[str] = None


class DetectedComponent(BaseModel):
    """A single detected visual component in the slide image."""

    design_id: str = Field(..., description="Unique ID, e.g. nano-title-0")
    component_type: str = Field(
        ...,
        description="Type: title, subtitle, text_block, bullet_list, icon, chart, image, shape, logo, footer, header, character",
    )
    label: str = Field(..., description="Human-readable label")
    text_content: Optional[str] = Field(
        None, description="Detected text content (if text component)"
    )
    bounding_box: BoundingBox
    z_index: int = 1
    confidence: float = 0.0
    styles: Optional[ComponentStyles] = None


class DetectRequest(BaseModel):
    """Request to detect components in a slide image."""

    session_id: str
    presentation_name: str
    slide_number: int = Field(..., ge=1)
    image_url: str
    force_refresh: bool = False  # Bypass cache


class DetectResponse(BaseModel):
    """Response with detected components."""

    success: bool
    slide_number: int
    components: List[DetectedComponent] = []
    image_width: int = 1280
    image_height: int = 720
    overlay_html: Optional[str] = None
    cached: bool = False
    error: Optional[str] = None


# ============ Selection & Instructions ============


class Selection(BaseModel):
    """Describes what the user selected."""

    type: SelectionType

    # For COMPONENT selection
    component_id: Optional[str] = None  # design_id of selected component

    # For SPOT selection (single point)
    spot_x: Optional[float] = Field(None, ge=0, le=100, description="X as % of image width")
    spot_y: Optional[float] = Field(None, ge=0, le=100, description="Y as % of image height")

    # For BOX selection (rectangular region)
    box: Optional[BoundingBox] = None


class Instruction(BaseModel):
    """A single edit instruction."""

    id: str  # Unique ID for this instruction
    selection: Selection  # What is being modified
    instruction_type: InstructionType

    # For text_edit
    new_text: Optional[str] = None

    # For ai_modify
    ai_prompt: Optional[str] = None  # User's instruction (e.g., "change to red")

    # Metadata
    timestamp: int  # Unix timestamp ms


# ============ Regeneration ============


class RegenerateRequest(BaseModel):
    """Request to regenerate slide with instructions."""

    session_id: str
    presentation_name: str
    slide_number: int = Field(..., ge=1)
    current_image_url: str
    instructions: List[Instruction]
    detected_components: Optional[List[DetectedComponent]] = None  # For context in prompt


class RegenerateResponse(BaseModel):
    """Response from slide regeneration."""

    success: bool
    new_image_url: Optional[str] = None
    new_version_id: Optional[str] = None
    version_number: Optional[int] = None
    error: Optional[str] = None


# ============ Remove Background ============


class RemoveBackgroundRequest(BaseModel):
    """Request to remove background from slide."""

    session_id: str
    presentation_name: str
    slide_number: int = Field(..., ge=1)
    image_url: str


class RemoveBackgroundResponse(BaseModel):
    """Response from background removal."""

    success: bool
    new_image_url: Optional[str] = None
    new_version_id: Optional[str] = None
    error: Optional[str] = None


# ============ Version History ============


class SlideVersionInfo(BaseModel):
    """Information about a slide version."""

    id: str
    version: int
    image_url: str
    thumbnail_url: Optional[str] = None
    edit_summary: Optional[str] = None
    created_at: str  # ISO format
    is_current: bool = False


class GetVersionsResponse(BaseModel):
    """Response with version history."""

    versions: List[SlideVersionInfo]
    current_version_id: Optional[str] = None


class RevertRequest(BaseModel):
    """Request to revert to a previous version."""

    session_id: str
    presentation_name: str
    slide_number: int = Field(..., ge=1)
    target_version_id: str


class RevertResponse(BaseModel):
    """Response from revert operation."""

    success: bool
    new_version_id: Optional[str] = None  # Revert creates a new version
    new_image_url: Optional[str] = None
    error: Optional[str] = None
