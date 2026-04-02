"""Storybook management API endpoints."""

import logging
import json
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Query, Response
from fastapi.responses import StreamingResponse

from ii_agent.core.exceptions import ValidationError
from ii_agent.sessions.dependencies import SessionServiceDep
from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.content.storybook.exceptions import (
    StorybookAccessDeniedError,
    StorybookExportError,
    StorybookNotFoundError,
    StorybookPageNotFoundError,
    StorybookVersionError,
)
from ii_agent.content.storybook.dependencies import (
    StorybookServiceDep,
    StorybookExportServiceDep,
    StorybookVersionServiceDep,
    StorybookVoiceServiceDep,
)
from ii_agent.content.storybook.schemas import (
    StorybookDetail,
    StorybookGenerationResponse,
    StorybookListResponse,
    StorybookVoiceOverResponse,
    PageTextUpdateRequest,
    PageRegenerateRequest,
    StorybookVersionResponse,
)
from ii_agent.auth.users.dependencies import UserServiceDep
from ii_agent.content.media.service import _generate_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/storybooks", tags=["Storybooks"])


@router.get("/session/{session_id}", response_model=StorybookListResponse)
async def get_session_storybooks(
    session_id: str,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
    include_pages: bool = Query(False, description="Include page data"),
) -> StorybookListResponse:
    """Get all storybooks for a session."""
    session_data = await session_service.get_session_details(db,
        session_id, str(current_user.id)
    )
    if not session_data:
        raise SessionNotFoundError(f"Session {session_id} not found or access denied")

    return await service.get_session_storybooks(
        db,
        session_id=session_id,
        include_pages=include_pages,
    )


@router.get("/{storybook_id}", response_model=StorybookDetail)
async def get_storybook(
    storybook_id: str,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
) -> StorybookDetail:
    """Get a storybook with all pages."""
    storybook = await service.get_storybook_detail(
        db,
        storybook_id=storybook_id,
        include_pages=True,
    )
    if not storybook:
        raise StorybookNotFoundError(f"Storybook {storybook_id} not found")

    session_data = await session_service.get_session_details(db,
        storybook.session_id, str(current_user.id)
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    return storybook


def _format_content_disposition(filename: str) -> str:
    """Format Content-Disposition header with proper UTF-8 encoding."""
    filename_ascii = filename.encode("ascii", "ignore").decode("ascii") or "download"
    filename_encoded = quote(filename)
    return f"attachment; filename=\"{filename_ascii}\"; filename*=UTF-8''{filename_encoded}"


@router.post("/{storybook_id}/voice", response_model=StorybookVoiceOverResponse)
async def generate_storybook_voiceover(
    storybook_id: str,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    voice_service: StorybookVoiceServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
    language: Optional[str] = Query(
        None, description="Optional language code for voice narration"
    ),
    force: bool = Query(
        False, description="Regenerate voice-over even if audio already exists"
    ),
) -> StorybookVoiceOverResponse:
    """Generate voice-over audio for a storybook."""
    storybook = await service.get_storybook_detail(
        db, storybook_id=storybook_id, include_pages=True
    )
    if not storybook:
        raise StorybookNotFoundError(f"Storybook {storybook_id} not found")

    session_data = await session_service.get_session_details(
        db, storybook.session_id, str(current_user.id)
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    return await voice_service.generate_voiceover_and_deduct_credits(
        db,
        storybook_id=storybook_id,
        user_id=str(current_user.id),
        session_id=storybook.session_id,
        language_code=language,
        force=force,
    )


@router.get("/{storybook_id}/progress", response_model=StorybookGenerationResponse)
async def get_storybook_progress(
    storybook_id: str,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
) -> StorybookGenerationResponse:
    """Get storybook generation progress for polling."""
    storybook = await service.get_storybook_detail(
        db, storybook_id=storybook_id, include_pages=True
    )
    if not storybook:
        raise StorybookNotFoundError(f"Storybook {storybook_id} not found")

    session_data = await session_service.get_session_details(
        db, storybook.session_id, str(current_user.id)
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    return service.build_generation_response(storybook)


@router.post("/{storybook_id}/cancel")
async def cancel_storybook_generation(
    storybook_id: str,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    voice_service: StorybookVoiceServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
) -> dict:
    """Cancel storybook generation for a storybook."""
    storybook = await service.get_storybook_detail(
        db, storybook_id=storybook_id, include_pages=False
    )
    if not storybook:
        raise StorybookNotFoundError(f"Storybook {storybook_id} not found")

    session_data = await session_service.get_session_details(
        db, storybook.session_id, str(current_user.id)
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    generation_status = voice_service.get_generation_status(storybook)

    if generation_status == "completed":
        return {"success": False, "message": "Storybook generation already completed."}

    if generation_status == "failed":
        return {"success": False, "message": "Storybook generation already stopped."}

    await voice_service.cancel_generation(db, storybook_id)
    return {"success": True, "message": "Storybook generation cancelled."}


@router.post(
    "/{storybook_id}/pages/{page_number}/text",
    response_model=StorybookVersionResponse,
)
async def update_page_text(
    storybook_id: str,
    page_number: int,
    request: PageTextUpdateRequest,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    version_service: StorybookVersionServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
) -> StorybookVersionResponse:
    """Update page text only (auto-creates new version)."""
    storybook = await service.get_storybook_detail(
        db,
        storybook_id=storybook_id,
        include_pages=False,
    )
    if not storybook:
        raise StorybookNotFoundError(f"Storybook {storybook_id} not found")

    session_data = await session_service.get_session_details(db,
        storybook.session_id, str(current_user.id)
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    new_storybook = await version_service.update_page_text(
        db,
        storybook_id=storybook_id,
        page_number=page_number,
        new_text=request.text_content,
    )
    if not new_storybook:
        raise StorybookVersionError("Failed to create new storybook version")

    return StorybookVersionResponse(success=True, storybook=new_storybook)


@router.post(
    "/{storybook_id}/pages/{page_number}/regenerate",
    response_model=StorybookVersionResponse,
)
async def regenerate_page_image(
    storybook_id: str,
    page_number: int,
    request: PageRegenerateRequest,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    version_service: StorybookVersionServiceDep,
    session_service: SessionServiceDep,
    user_service: UserServiceDep,
    db: DBSession,
) -> StorybookVersionResponse:
    """Regenerate page image with new/same prompt (auto-creates new version)."""
    storybook = await service.get_storybook_detail(
        db,
        storybook_id=storybook_id,
        include_pages=False,
    )
    if not storybook:
        raise StorybookNotFoundError(f"Storybook {storybook_id} not found")

    session_data = await session_service.get_session_details(db,
        storybook.session_id, str(current_user.id)
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    user_api_key = await user_service.get_active_api_key(db, str(current_user.id))
    if not user_api_key:
        raise ValidationError("No active API key found for user")

    async def generate_image_wrapper(
        prompt: str,
        user_api_key: str,
        session_id: str,
        aspect_ratio: str,
        resolution: str,
    ) -> str:
        output =  await _generate_image(
            prompt=prompt,
            session_id=session_id,
            user_api_key=user_api_key,
        )
        return output.get("url", "")

    new_storybook = await version_service.regenerate_page_image(
        db,
        storybook_id=storybook_id,
        page_number=page_number,
        new_image_prompt=request.image_prompt,
        generate_image_func=generate_image_wrapper,
        user_api_key=user_api_key,
        session_id=storybook.session_id,
    )
    if not new_storybook:
        raise StorybookVersionError("Failed to create new storybook version")

    return StorybookVersionResponse(success=True, storybook=new_storybook)


@router.get("/{storybook_id}/download")
async def download_storybook(
    storybook_id: str,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    export_service: StorybookExportServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
):
    """Download storybook as PDF."""
    storybook = await service.get_storybook_detail(
        db,
        storybook_id=storybook_id,
        include_pages=False,
    )
    if not storybook:
        raise StorybookNotFoundError(f"Storybook {storybook_id} not found")

    session_data = await session_service.get_session_details(db,
        storybook.session_id, str(current_user.id)
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    pdf_bytes = await export_service.download_storybook_as_pdf(db, storybook_id)
    if not pdf_bytes:
        raise StorybookExportError("Failed to generate PDF")

    filename = f"{storybook.name.replace(' ', '_')}_{storybook_id[:8]}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": _format_content_disposition(filename),
        },
    )


@router.get("/{storybook_id}/download/stream")
async def download_storybook_with_progress(
    storybook_id: str,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    export_service: StorybookExportServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
):
    """Download storybook as PDF with progress updates via SSE."""
    storybook = await service.get_storybook_detail(
        db,
        storybook_id=storybook_id,
        include_pages=False,
    )
    if not storybook:
        raise StorybookNotFoundError(f"Storybook {storybook_id} not found")

    session_data = await session_service.get_session_details(db,
        storybook.session_id, str(current_user.id)
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    async def generate_events():
        async for progress_data in export_service.download_storybook_as_pdf_with_progress(
            db, storybook_id
        ):
            yield f"data: {json.dumps(progress_data)}\n\n"

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/{storybook_id}/download/page/{page_number}")
async def download_storybook_page_pdf(
    storybook_id: str,
    page_number: int,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    export_service: StorybookExportServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
):
    """Download a single storybook page as PDF."""
    storybook = await service.get_storybook_detail(
        db,
        storybook_id=storybook_id,
        include_pages=False,
    )
    if not storybook:
        raise StorybookNotFoundError(f"Storybook {storybook_id} not found")

    session_data = await session_service.get_session_details(db,
        storybook.session_id, str(current_user.id)
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    pdf_bytes = await export_service.download_storybook_page_as_pdf(
        db, storybook_id, page_number
    )
    if not pdf_bytes:
        raise StorybookPageNotFoundError(f"Page {page_number} not found or has no content")

    filename = f"{storybook.name.replace(' ', '_')}_page_{page_number}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": _format_content_disposition(filename),
        },
    )


@router.get("/{storybook_id}/download/png/{page_number}")
async def download_storybook_page_png(
    storybook_id: str,
    page_number: int,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    export_service: StorybookExportServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
):
    """Download a single storybook page as PNG."""
    storybook = await service.get_storybook_detail(
        db,
        storybook_id=storybook_id,
        include_pages=False,
    )
    if not storybook:
        raise StorybookNotFoundError(f"Storybook {storybook_id} not found")

    session_data = await session_service.get_session_details(db,
        storybook.session_id, str(current_user.id)
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    png_bytes = await export_service.download_storybook_page_as_png(
        db, storybook_id, page_number
    )
    if not png_bytes:
        raise StorybookPageNotFoundError(f"Page {page_number} not found or has no content")

    filename = f"{storybook.name.replace(' ', '_')}_page_{page_number}.png"

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": _format_content_disposition(filename),
        },
    )


@router.get("/{storybook_id}/download/png")
async def download_storybook_png_zip(
    storybook_id: str,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    export_service: StorybookExportServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
):
    """Download all storybook pages as a ZIP of PNGs."""
    storybook = await service.get_storybook_detail(
        db,
        storybook_id=storybook_id,
        include_pages=False,
    )
    if not storybook:
        raise StorybookNotFoundError(f"Storybook {storybook_id} not found")

    session_data = await session_service.get_session_details(db,
        storybook.session_id, str(current_user.id)
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    zip_bytes = await export_service.download_storybook_as_png_zip(db, storybook_id)
    if not zip_bytes:
        raise StorybookExportError("Failed to generate PNG files")

    filename = f"{storybook.name.replace(' ', '_')}_{storybook_id[:8]}-pages.zip"

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": _format_content_disposition(filename),
        },
    )


@router.get("/{storybook_id}/download/png/stream")
async def download_storybook_png_with_progress(
    storybook_id: str,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    export_service: StorybookExportServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
):
    """Download all storybook pages as a ZIP of PNGs with progress updates via SSE."""
    storybook = await service.get_storybook_detail(
        db,
        storybook_id=storybook_id,
        include_pages=False,
    )
    if not storybook:
        raise StorybookNotFoundError(f"Storybook {storybook_id} not found")

    session_data = await session_service.get_session_details(db,
        storybook.session_id, str(current_user.id)
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    async def generate_events():
        async for progress_data in export_service.download_storybook_as_png_with_progress(
            db, storybook_id
        ):
            yield f"data: {json.dumps(progress_data)}\n\n"

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# Public endpoint for shared storybooks
@router.get("/public/{storybook_id}", response_model=StorybookDetail)
async def get_public_storybook(
    storybook_id: str,
    service: StorybookServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
) -> StorybookDetail:
    """Get a public storybook with all pages (no auth required)."""
    storybook = await service.get_storybook_detail(
        db,
        storybook_id=storybook_id,
        include_pages=True,
    )
    if not storybook:
        raise StorybookNotFoundError(f"Storybook {storybook_id} not found")

    session_data = await session_service.get_public_session_details(db,storybook.session_id)
    if not session_data:
        raise StorybookNotFoundError("Storybook not found or not public")

    return storybook
