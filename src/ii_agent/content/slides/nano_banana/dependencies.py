"""FastAPI dependencies for Nano Banana design mode."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends

from ii_agent.content.slides.dependencies import SlideRepositoryDep
from ii_agent.sessions.dependencies import SessionRepositoryDep

from .repository import NanoBananaRepository
from .service import NanoBananaService


def get_nano_banana_repository(
    session_repo: SessionRepositoryDep,
    slide_repo: SlideRepositoryDep,
) -> NanoBananaRepository:
    """Provide NanoBananaRepository instance."""
    return NanoBananaRepository(session_repo=session_repo, slide_repo=slide_repo)


NanoBananaRepositoryDep = Annotated[NanoBananaRepository, Depends(get_nano_banana_repository)]


def get_nano_banana_service(
    repo: NanoBananaRepositoryDep,
) -> NanoBananaService:
    """Provide NanoBananaService instance with Gemini config from environment."""
    return NanoBananaService(
        repo=repo,
        gemini_api_key=os.environ.get("GEMINI_API_KEY"),
        gcp_project_id=os.environ.get("SLIDE_ASSETS_PROJECT_ID"),
        gcp_location=os.environ.get("GCP_LOCATION", "us-central1"),
    )


NanoBananaServiceDep = Annotated[NanoBananaService, Depends(get_nano_banana_service)]


__all__ = [
    "get_nano_banana_repository",
    "get_nano_banana_service",
    "NanoBananaRepositoryDep",
    "NanoBananaServiceDep",
]
