"""FastAPI router for Nano Banana design mode endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ii_agent.auth.dependencies import CurrentUser, DBSession

from .dependencies import NanoBananaServiceDep
from .schemas import (
    DetectRequest,
    DetectResponse,
    GetVersionsResponse,
    RegenerateRequest,
    RegenerateResponse,
    RemoveBackgroundRequest,
    RemoveBackgroundResponse,
    RevertRequest,
    RevertResponse,
)

router = APIRouter(
    prefix="/slides/nano-banana",
    tags=["Slide Design Mode - Nano Banana"],
)


@router.post("/detect", response_model=DetectResponse)
async def detect_components(
    request: DetectRequest,
    current_user: CurrentUser,
    db: DBSession,
    service: NanoBananaServiceDep,
) -> DetectResponse:
    """Detect visual components in a slide image using Gemini Vision.

    Analyzes a slide image and returns detected components with their
    bounding boxes, text content, and estimated styles. Results include
    an interactive overlay HTML for editing.
    """
    return await service.detect_components(
        db,
        user_id=str(current_user.id),
        request=request,
    )


@router.post("/regenerate", response_model=RegenerateResponse)
async def regenerate_slide(
    request: RegenerateRequest,
    current_user: CurrentUser,
    db: DBSession,
    service: NanoBananaServiceDep,
) -> RegenerateResponse:
    """Regenerate a slide image with user-specified modifications.

    Takes the current slide image and a list of instructions (text edits,
    AI modifications, etc.) and generates a new version with those changes.
    A new version is created and the SlideContent is updated.
    """
    return await service.regenerate_slide(
        db,
        user_id=str(current_user.id),
        request=request,
    )


@router.post("/remove-background", response_model=RemoveBackgroundResponse)
async def remove_background(
    request: RemoveBackgroundRequest,
    current_user: CurrentUser,
    db: DBSession,
    service: NanoBananaServiceDep,
) -> RemoveBackgroundResponse:
    """Remove the background from a slide image.

    Replaces the background with white while preserving all foreground
    elements (text, icons, characters, etc.).
    """
    return await service.remove_background(
        db,
        user_id=str(current_user.id),
        request=request,
    )


@router.get("/versions", response_model=GetVersionsResponse)
async def get_versions(
    current_user: CurrentUser,
    db: DBSession,
    service: NanoBananaServiceDep,
    session_id: str = Query(..., description="Session ID"),
    presentation_name: str = Query(..., description="Presentation name"),
    slide_number: int = Query(..., ge=1, description="Slide number"),
) -> GetVersionsResponse:
    """Get version history for a slide.

    Returns all versions ordered by version number descending.
    The current version is marked with is_current=True.
    """
    return await service.get_versions(
        db,
        user_id=str(current_user.id),
        session_id=session_id,
        presentation_name=presentation_name,
        slide_number=slide_number,
    )


@router.post("/revert", response_model=RevertResponse)
async def revert_to_version(
    request: RevertRequest,
    current_user: CurrentUser,
    db: DBSession,
    service: NanoBananaServiceDep,
) -> RevertResponse:
    """Revert a slide to a previous version.

    Creates a new version with the same image as the target version,
    preserving the full history.
    """
    return await service.revert_to_version(
        db,
        user_id=str(current_user.id),
        request=request,
    )
