"""API routes for media domain.

Consolidated from:
- server/media_tools/views.py
- server/media_templates/views.py
- server/api/media.py
- legacy_media/media.py (model config endpoints, optional session_id)
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Query

from ii_agent.content.media.constants import IMAGE_CONFIG_PATH, VIDEO_CONFIG_PATH
from ii_agent.content.media.exceptions import MediaTemplateNotFoundError
from ii_agent.core.exceptions import InternalError, ValidationError
from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.content.media.dependencies import MediaTemplateServiceDep
from ii_agent.core.storage.dependencies import StorageServiceDep
from ii_agent.content.media.schemas import (
    ImageModelsResponse,
    MediaModelConfig,
    MediaTemplateInfo,
    MediaTool,
    ReferenceImageRequest,
    ReferenceImageResponse,
    VideoModelsResponse,
)
from ii_agent.content.media.utils import load_yaml_config
from ii_agent.sessions.dependencies import SessionServiceDep
from ii_agent.users.dependencies import UserServiceDep
from ii_agent.files.dependencies import FileServiceDep

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Media Templates Routes
# =============================================================================

templates_router = APIRouter(prefix="/media-templates", tags=["Media Templates"])


@templates_router.get("")
async def list_media_templates(
    media_template_service: MediaTemplateServiceDep,
    db: DBSession,
    page: int = Query(0, ge=0, description="Page number (0-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Number of templates per page"),
    name: Optional[str] = Query(None, description="Search in template name"),
    type: Optional[str] = Query(None, description="Filter by media type (e.g., image, video)"),
):
    """Get a paginated list of media templates."""
    return await media_template_service.list_media_templates(
        db,
        page=page,
        page_size=page_size,
        search=name,
        media_type=type,
    )


@templates_router.get("/{template_id}", response_model=MediaTemplateInfo)
async def get_media_template(
    template_id: uuid.UUID,
    media_template_service: MediaTemplateServiceDep,
    db: DBSession,
):
    """Get a specific media template by ID."""
    template = await media_template_service.get_media_template_by_id(db, template_id)
    if not template:
        raise MediaTemplateNotFoundError("Template not found")
    return template


# =============================================================================
# Media Tools Routes
# =============================================================================

tools_router = APIRouter(prefix="/media-tools", tags=["Media Tools"])


@tools_router.get("", response_model=list[MediaTool])
async def list_media_tools_endpoint(
    media_template_service: MediaTemplateServiceDep,
    db: DBSession,
    page: int = Query(0, ge=0, description="Page number (0-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Number of tools per page"),
    name: Optional[str] = Query(None, description="Search in mini tool name"),
):
    """List mini tools stored in media_templates (type = image-mini-tools)."""
    return await media_template_service.list_media_tools(
        db,
        page=page,
        page_size=page_size,
        name=name,
    )


@tools_router.get("/{tool_id}", response_model=MediaTool)
async def get_media_tool_endpoint(
    tool_id: str,
    media_template_service: MediaTemplateServiceDep,
    db: DBSession,
):
    """Get a media mini tool definition by id (type = image-mini-tools)."""
    media_tool = await media_template_service.get_media_tool(db, tool_id)
    if not media_tool:
        raise MediaTemplateNotFoundError("Media tool not found")
    return media_tool


# =============================================================================
# Reference Image Routes
# =============================================================================

reference_router = APIRouter(prefix="/media", tags=["Media"])


@reference_router.post("/reference-image", response_model=ReferenceImageResponse)
async def generate_reference_image(
    request: ReferenceImageRequest,
    current_user: CurrentUser,
    db: DBSession,
    session_service: SessionServiceDep,
    user_service: UserServiceDep,
    file_service: FileServiceDep,
    default_storage: StorageServiceDep,
    media_template_service: MediaTemplateServiceDep,
):
    """Generate a reference image based on type (subject/scene/style).

    Supports optional session_id. When session_id is None the generated image
    is stored under the user's personal storage path instead of a session.
    """
    session_id = request.session_id
    if session_id in {"", "null", "None"}:
        session_id = None

    # Verify session ownership when provided
    if session_id:
        session_data = await session_service.get_session_details(
            db, session_id, str(current_user.id)
        )
        if not session_data:
            raise SessionNotFoundError(f"Session {session_id} not found or access denied")

    user_api_key = await user_service.get_active_api_key(db, current_user.id)
    if not user_api_key:
        raise ValidationError("No active API key found")

    return await media_template_service.generate_reference_image(
        db,
        user_id=current_user.id,
        prompt=request.prompt,
        reference_type=request.type,
        aspect_ratio=request.aspect_ratio,
        session_id=session_id,
        user_api_key=user_api_key,
        model_name=request.model_name,
        provider=request.provider,
        default_storage=default_storage,
        file_service=file_service,
    )


# =============================================================================
# Media Model Config Routes (ported from legacy_media/media.py)
# =============================================================================


@reference_router.get("/models/video", response_model=VideoModelsResponse)
async def get_video_models():
    """Get all available video generation models and their configurations."""
    try:
        config = load_yaml_config(VIDEO_CONFIG_PATH)
    except FileNotFoundError as e:
        logger.error(f"Video config file not found: {e}")
        raise InternalError("Video configuration not found") from e

    return VideoModelsResponse(
        models=[MediaModelConfig(**model) for model in config.get("models", [])],
        suggestions=config.get("suggestions", []),
    )


@reference_router.get("/models/image", response_model=ImageModelsResponse)
async def get_image_models():
    """Get all available image generation models and their configurations."""
    try:
        config = load_yaml_config(IMAGE_CONFIG_PATH)
    except FileNotFoundError as e:
        logger.error(f"Image config file not found: {e}")
        raise InternalError("Image configuration not found") from e

    return ImageModelsResponse(
        models=[MediaModelConfig(**model) for model in config.get("models", [])],
        storybook_models=[
            MediaModelConfig(**model) for model in config.get("storybook_models", [])
        ],
        suggestions=config.get("suggestions", []),
        storybook_suggestions=config.get("storybook_suggestions", []),
    )


# Include sub-routers
router.include_router(templates_router)
router.include_router(tools_router)
router.include_router(reference_router)
