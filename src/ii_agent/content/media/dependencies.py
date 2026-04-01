"""FastAPI dependencies for media domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep
from ii_agent.content.media.repository import MediaTemplateRepository
from ii_agent.content.media.service import MediaTemplateService


# ==================== Repository Dependencies ====================


def get_media_template_repository() -> MediaTemplateRepository:
    """Provide MediaTemplateRepository instance."""
    return MediaTemplateRepository()


MediaTemplateRepositoryDep = Annotated[MediaTemplateRepository, Depends(get_media_template_repository)]


# ==================== Service Dependencies ====================


def _get_media_template_service(container: ContainerDep) -> MediaTemplateService:
    return container.media_template_service


MediaTemplateServiceDep = Annotated[
    MediaTemplateService, Depends(_get_media_template_service)
]


__all__ = [
    "get_media_template_repository",
    "MediaTemplateRepositoryDep",
    "MediaTemplateServiceDep",
]
