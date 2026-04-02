"""Slide management API endpoints."""

from typing import Optional
from fastapi import APIRouter, Query
from fastapi.responses import Response, StreamingResponse
import json

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.content.slides.dependencies import SlideServiceDep
from ii_agent.content.slides.exceptions import SlideNotFoundError
from ii_agent.content.slides.schemas import (
    SlideWriteRequest,
    SlideWriteResponse,
    PresentationListResponse,
)
from ii_agent.content.slides.templates.router import router as templates_router
from ii_agent.content.slides.design.router import router as design_router
from ii_agent.content.slides.nano_banana.router import router as nano_banana_router

router = APIRouter(prefix="/slides", tags=["Slide Management"])
router.include_router(templates_router)
router.include_router(design_router)
router.include_router(nano_banana_router)


@router.post("", response_model=SlideWriteResponse)
async def write_slide(
    write_request: SlideWriteRequest,
    current_user: CurrentUser,
    slide_service: SlideServiceDep,
    db: DBSession,
    session_id: str = Query(..., description="Session ID"),
):
    """Create or overwrite slide content. Updates filesystem and database."""

    result = await slide_service.execute_slide_write(
        db,
        write_request=write_request,
        session_id=session_id,
        user_id=current_user.id,
    )

    return result


@router.get("", response_model=PresentationListResponse)
async def list_presentations(
    current_user: CurrentUser,
    slide_service: SlideServiceDep,
    db: DBSession,
    session_id: str = Query(..., description="Session ID"),
):
    """Get list of presentations in session from database."""

    result = await slide_service.get_session_presentations(
        db,
        session_id=session_id,
        user_id=current_user.id,
    )

    return result


@router.get("/download")
async def download_slides(
    current_user: CurrentUser,
    slide_service: SlideServiceDep,
    db: DBSession,
    session_id: str = Query(..., description="Session ID"),
    presentation_name: Optional[str] = Query(None, description="Specific presentation to download"),
):
    """Download slides as PDF for authenticated users."""

    pdf_bytes = await slide_service.download_session_slides_as_pdf(
        db,
        session_id=session_id,
        user_id=current_user.id,
        presentation_name=presentation_name,
    )

    if not pdf_bytes:
        raise SlideNotFoundError("No slides found or access denied")

    filename = f"slides_{session_id}"
    if presentation_name:
        filename = f"{presentation_name}_{session_id}"
    filename += ".pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/download/stream")
async def download_slides_with_progress(
    current_user: CurrentUser,
    slide_service: SlideServiceDep,
    db: DBSession,
    session_id: str = Query(..., description="Session ID"),
    presentation_name: Optional[str] = Query(None, description="Specific presentation to download"),
):
    """Download slides as PDF with progress updates via Server-Sent Events."""

    async def generate_progress():
        try:
            async for progress_data in slide_service.download_session_slides_as_pdf_with_progress(
                db,
                session_id=session_id,
                user_id=current_user.id,
                presentation_name=presentation_name,
            ):
                yield f"data: {json.dumps(progress_data)}\n\n"

        except Exception as e:
            error_data = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Public endpoints (served under /v1/public/slides)
# ---------------------------------------------------------------------------

public_router = APIRouter(prefix="/slides", tags=["Slides Public"])


@public_router.get("", response_model=PresentationListResponse)
async def list_public_presentations(
    slide_service: SlideServiceDep,
    db: DBSession,
    session_id: str = Query(..., description="Session ID"),
):
    """Get list of presentations from a public session."""

    result = await slide_service.get_public_session_presentations(
        db,
        session_id=session_id,
    )

    return result


@public_router.get("/download")
async def download_public_slides(
    slide_service: SlideServiceDep,
    db: DBSession,
    session_id: str = Query(..., description="Session ID"),
    presentation_name: Optional[str] = Query(None, description="Specific presentation to download"),
):
    """Download slides as PDF from a public session."""

    pdf_bytes = await slide_service.download_public_session_slides_as_pdf(
        db, session_id=session_id, presentation_name=presentation_name
    )

    if not pdf_bytes:
        raise SlideNotFoundError("No slides found or session is not public")

    filename = f"slides_{session_id}"
    if presentation_name:
        filename = f"{presentation_name}_{session_id}"
    filename += ".pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@public_router.get("/download/stream")
async def download_public_slides_with_progress(
    slide_service: SlideServiceDep,
    db: DBSession,
    session_id: str = Query(..., description="Session ID"),
    presentation_name: Optional[str] = Query(None, description="Specific presentation to download"),
):
    """Download public slides as PDF with progress updates via Server-Sent Events."""

    async def generate_progress():
        try:
            async for (
                progress_data
            ) in slide_service.download_public_session_slides_as_pdf_with_progress(
                db,
                session_id=session_id,
                presentation_name=presentation_name,
            ):
                yield f"data: {json.dumps(progress_data)}"

        except Exception as e:
            error_data = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(error_data)}"

    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
