"""Media generation (templates, tools) domain module."""

from .models import MediaTemplate
from .repository import MediaTemplateRepository
from .service import MediaTemplateService
from .router import router
from .schemas import (
    MediaModelConfig,
    MediaTemplateInfo,
    MediaTemplateListItem,
    MediaTemplatesListResponse,
    MediaTool,
    ReferenceImageRequest,
    ReferenceImageResponse,
    ImageModelsResponse,
    VideoModelsResponse,
)
from .exceptions import MediaTemplateNotFoundError

__all__ = [
    # Models
    "MediaTemplate",
    # Repository
    "MediaTemplateRepository",
    # Service
    "MediaTemplateService",
    # Router
    "router",
    # Schemas
    "MediaModelConfig",
    "MediaTemplateInfo",
    "MediaTemplateListItem",
    "MediaTemplatesListResponse",
    "MediaTool",
    "ReferenceImageRequest",
    "ReferenceImageResponse",
    "ImageModelsResponse",
    "VideoModelsResponse",
    # Exceptions
    "MediaTemplateNotFoundError",
]
