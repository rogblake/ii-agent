"""FastAPI dependencies for media domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.core.storage.client import media_storage
from ii_agent.content.media.repository import MediaTemplateRepository
from ii_agent.content.media.service import MediaTemplateService


# ==================== Repository Dependencies ====================


def get_media_template_repository() -> MediaTemplateRepository:
    """Provide MediaTemplateRepository instance."""
    return MediaTemplateRepository()


MediaTemplateRepositoryDep = Annotated[MediaTemplateRepository, Depends(get_media_template_repository)]


# ==================== Service Dependencies ====================


def get_media_template_service(
    repo: MediaTemplateRepositoryDep,
) -> MediaTemplateService:
    """Provide MediaTemplateService instance with explicit repo injection."""
    return MediaTemplateService(
        repo=repo,
        media_storage=media_storage,
        config=get_settings(),
    )


MediaTemplateServiceDep = Annotated[
    MediaTemplateService, Depends(get_media_template_service)
]


__all__ = [
    "get_media_template_repository",
    "get_media_template_service",
    "MediaTemplateRepositoryDep",
    "MediaTemplateServiceDep",
]
