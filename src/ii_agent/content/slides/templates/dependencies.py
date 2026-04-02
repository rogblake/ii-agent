"""FastAPI dependencies for slide templates subdomain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.content.slides.templates.repository import SlideTemplateRepository
from ii_agent.content.slides.templates.service import SlideTemplateService


# ==================== Repository Dependencies ====================


def get_slide_template_repository() -> SlideTemplateRepository:
    """Provide SlideTemplateRepository instance."""
    return SlideTemplateRepository()


SlideTemplateRepositoryDep = Annotated[
    SlideTemplateRepository, Depends(get_slide_template_repository)
]


# ==================== Service Dependencies ====================


def get_slide_template_service(
    template_repo: SlideTemplateRepositoryDep,
) -> SlideTemplateService:
    """Provide SlideTemplateService instance with explicit config."""
    return SlideTemplateService(
        template_repo=template_repo,
        config=get_settings(),
    )


SlideTemplateServiceDep = Annotated[
    SlideTemplateService, Depends(get_slide_template_service)
]


__all__ = [
    "get_slide_template_repository",
    "SlideTemplateRepositoryDep",
    "get_slide_template_service",
    "SlideTemplateServiceDep",
]
