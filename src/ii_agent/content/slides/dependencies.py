"""FastAPI dependencies for slides domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.sessions.dependencies import SessionRepositoryDep
from ii_agent.content.slides.repository import SlideContentRepository
from ii_agent.content.slides.service import SlideService


# ==================== Repository Dependencies ====================


def get_slide_repository() -> SlideContentRepository:
    """Provide SlideContentRepository instance."""
    return SlideContentRepository()


SlideRepositoryDep = Annotated[SlideContentRepository, Depends(get_slide_repository)]


# ==================== Service Dependencies ====================
# Note: SlideService is NOT in ApplicationContainer — it uses inline
# construction with per-request repo injection.


def get_slide_service(
    slide_repo: SlideRepositoryDep,
    session_repo: SessionRepositoryDep,
) -> SlideService:
    """Provide SlideService instance with explicit repo injection."""
    return SlideService(
        slide_repo=slide_repo,
        session_repo=session_repo,
        config=get_settings(),
    )


SlideServiceDep = Annotated[SlideService, Depends(get_slide_service)]


__all__ = [
    "get_slide_repository",
    "get_slide_service",
    "SlideRepositoryDep",
    "SlideServiceDep",
]
