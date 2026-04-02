"""Storybook management API endpoints."""

import logging
import json
import uuid
from typing import Dict, List, Optional
from urllib.parse import quote
from pathlib import Path

from fastapi import APIRouter, File, Query, Response, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse

from ii_agent.billing.exceptions import InsufficientCreditsError
from ii_agent.core.exceptions import PaymentRequiredError, ValidationError
from ii_agent.sessions.dependencies import SessionServiceDep
from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.credits.dependencies import CreditServiceDep
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
    StorybookEditServiceDep,
    StorybookAIEditServiceDep,
    StorybookVersionServiceDep,
    StorybookVoiceServiceDep,
)
from ii_agent.content.storybook.schemas import (
    DesignChange,
    SaveEditsRequest,
    SaveEditsResponse,
    StorybookDetail,
    StorybookGenerationResponse,
    StorybookListResponse,
    VersionHistoryResponse,
    StorybookVoiceOverResponse,
    PageTextUpdateRequest,
    PageRegenerateRequest,
    StorybookVersionResponse,
    StorybookBackgroundUploadResponse,
    AIRewriteRequest,
    AIRewriteResponse,
    AIGenerateBackgroundRequest,
    AIGenerateBackgroundResponse,
    AIRegenerateImageRequest,
    AIRegenerateImageResponse,
)
from ii_agent.users.dependencies import UserServiceDep
from ii_agent.content.media.service import _generate_image
from ii_agent.core.storage.dependencies import StorageServiceDep
from ii_agent.core.storage.path_resolver import path_resolver
from ii_agent.files.types import AssetType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/storybooks", tags=["Storybooks"])


@router.get("/session/{session_id}", response_model=StorybookListResponse)
async def get_session_storybooks(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
    include_pages: bool = Query(False, description="Include page data"),
) -> StorybookListResponse:
    """Get all storybooks for a session."""
    session_data = await session_service.get_session_details(db, session_id, current_user.id)
    if not session_data:
        raise SessionNotFoundError(f"Session {session_id} not found or access denied")

    return await service.get_session_storybooks(
        db,
        session_id=session_id,
        include_pages=include_pages,
    )


@router.get("/{storybook_id}", response_model=StorybookDetail)
async def get_storybook(
    storybook_id: uuid.UUID,
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

    session_data = await session_service.get_session_details(
        db, storybook.session_id, current_user.id
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
    storybook_id: uuid.UUID,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    voice_service: StorybookVoiceServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
    language: Optional[str] = Query(None, description="Optional language code for voice narration"),
    force: bool = Query(False, description="Regenerate voice-over even if audio already exists"),
) -> StorybookVoiceOverResponse:
    """Generate voice-over audio for a storybook."""
    storybook = await service.get_storybook_detail(
        db, storybook_id=storybook_id, include_pages=True
    )
    if not storybook:
        raise StorybookNotFoundError(f"Storybook {storybook_id} not found")

    session_data = await session_service.get_session_details(
        db, storybook.session_id, current_user.id
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    return await voice_service.generate_voiceover_and_deduct_credits(
        db,
        storybook_id=storybook_id,
        user_id=current_user.id,
        session_id=storybook.session_id,
        language_code=language,
        force=force,
    )


@router.get("/{storybook_id}/progress", response_model=StorybookGenerationResponse)
async def get_storybook_progress(
    storybook_id: uuid.UUID,
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
        db, storybook.session_id, current_user.id
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    return service.build_generation_response(storybook)


@router.post("/{storybook_id}/cancel")
async def cancel_storybook_generation(
    storybook_id: uuid.UUID,
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
        db, storybook.session_id, current_user.id
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
    storybook_id: uuid.UUID,
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

    session_data = await session_service.get_session_details(
        db, storybook.session_id, current_user.id
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
    storybook_id: uuid.UUID,
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

    session_data = await session_service.get_session_details(
        db, storybook.session_id, current_user.id
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    user_api_key = await user_service.get_active_api_key(db, current_user.id)
    if not user_api_key:
        logger.warning("No active API key found for user")

    async def generate_image_wrapper(
        prompt: str,
        user_api_key: str,
        session_id: str,
        aspect_ratio: str,
        resolution: str,
    ) -> str:
        output = await _generate_image(
            prompt=prompt,
            session_id=session_id,
            user_id=current_user.id,
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


@router.get("/{storybook_id}/edit/proxy", response_class=HTMLResponse)
async def proxy_storybook_edit_page(
    storybook_id: uuid.UUID,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    edit_service: StorybookEditServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
    page_number: int = Query(..., description="Page number (1-indexed)", ge=1),
) -> HTMLResponse:
    """Fetch storybook page HTML with design mode runtime injected."""
    storybook = await service.get_storybook_detail(
        db,
        storybook_id=storybook_id,
        include_pages=False,
    )
    if not storybook:
        raise StorybookNotFoundError(f"Storybook {storybook_id} not found")

    session_data = await session_service.get_session_details(
        db,
        storybook.session_id,
        current_user.id,
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    html_content = await edit_service.get_page_html_with_runtime(
        db,
        storybook_id=storybook_id,
        page_number=page_number,
    )
    if not html_content:
        raise StorybookPageNotFoundError(f"Page {page_number} not found or has no HTML content")

    return HTMLResponse(
        content=html_content,
        headers={
            "Content-Security-Policy": "frame-ancestors 'self'",
            "X-Frame-Options": "SAMEORIGIN",
        },
    )


@router.post("/{storybook_id}/edit/save", response_model=SaveEditsResponse)
async def save_storybook_edits(
    storybook_id: uuid.UUID,
    request: SaveEditsRequest,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    edit_service: StorybookEditServiceDep,
    credit_service: CreditServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
) -> SaveEditsResponse:
    """Apply visual edit changes and create one new storybook version."""
    storybook = await service.get_storybook_detail(
        db,
        storybook_id=storybook_id,
        include_pages=False,
    )
    if not storybook:
        return SaveEditsResponse(success=False, error="Storybook not found")

    session_data = await session_service.get_session_details(
        db,
        storybook.session_id,
        current_user.id,
    )
    if not session_data:
        return SaveEditsResponse(
            success=False,
            error="Access denied to this storybook",
        )

    if request.storybook_id != storybook_id:
        return SaveEditsResponse(
            success=False,
            error="Path storybook_id does not match request.storybook_id",
        )
    if not request.page_changes:
        return SaveEditsResponse(success=False, error="No changes to save")

    page_changes: Dict[int, List[DesignChange]] = {}
    image_urls: Dict[int, str] = {}
    for page_change in request.page_changes:
        if page_change.changes:
            page_changes[page_change.page_number] = page_change.changes
        if page_change.image_url:
            image_urls[page_change.page_number] = page_change.image_url

    if not page_changes and not image_urls:
        return SaveEditsResponse(success=False, error="No changes to save")

    if not await credit_service.has_sufficient_credits(db, current_user.id):
        raise InsufficientCreditsError(available_credits=0.0, required_credits=0.0)

    try:
        new_storybook = await edit_service.save_all_page_edits_with_billing(
            db,
            storybook_id=storybook_id,
            user_id=current_user.id,
            page_changes=page_changes,
            image_urls=image_urls,
        )
    except InsufficientCreditsError as exc:
        raise PaymentRequiredError(exc.message) from exc
    except Exception as exc:
        logger.error("Error saving storybook edits: %s", exc, exc_info=True)
        return SaveEditsResponse(success=False, error=f"Error saving changes: {exc}")

    if not new_storybook:
        return SaveEditsResponse(success=False, error="Failed to save changes")

    return SaveEditsResponse(success=True, storybook=new_storybook)


@router.get("/{storybook_id}/versions", response_model=VersionHistoryResponse)
async def get_storybook_versions(
    storybook_id: uuid.UUID,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    edit_service: StorybookEditServiceDep,
    session_service: SessionServiceDep,
    db: DBSession,
) -> VersionHistoryResponse:
    """Get version history for a storybook family."""
    storybook = await service.get_storybook_detail(
        db,
        storybook_id=storybook_id,
        include_pages=False,
    )
    if not storybook:
        raise StorybookNotFoundError(f"Storybook {storybook_id} not found")

    session_data = await session_service.get_session_details(
        db,
        storybook.session_id,
        current_user.id,
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    versions = await edit_service.get_version_history(
        db,
        storybook_id=storybook_id,
    )
    return VersionHistoryResponse(versions=versions)


@router.post(
    "/{storybook_id}/edit/upload-background",
    response_model=StorybookBackgroundUploadResponse,
)
async def upload_storybook_background(
    storybook_id: uuid.UUID,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    session_service: SessionServiceDep,
    media_storage: StorageServiceDep,
    db: DBSession,
    file: UploadFile = File(...),
) -> StorybookBackgroundUploadResponse:
    """Upload a storybook background/reference image."""
    storybook = await service.get_storybook_detail(
        db,
        storybook_id=storybook_id,
        include_pages=False,
    )
    if not storybook:
        raise StorybookNotFoundError(f"Storybook {storybook_id} not found")

    session_data = await session_service.get_session_details(
        db,
        storybook.session_id,
        current_user.id,
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    content_type = (file.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise ValidationError("Only image uploads are supported")

    suffix = Path(file.filename or "").suffix.lower()
    if not suffix:
        ext_map = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "image/avif": ".avif",
        }
        suffix = ext_map.get(content_type, ".png")

    storage_path = path_resolver.user_file(
        current_user.id, AssetType.IMAGE, uuid.uuid4().hex, suffix.lstrip(".")
    )
    await media_storage.write(storage_path, file.file, content_type)
    public_url = media_storage.public_url(storage_path)
    return StorybookBackgroundUploadResponse(url=public_url, storage_path=storage_path)


@router.post(
    "/{storybook_id}/edit/ai-rewrite",
    response_model=AIRewriteResponse,
)
async def ai_rewrite_storybook_content(
    storybook_id: uuid.UUID,
    request: AIRewriteRequest,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    session_service: SessionServiceDep,
    ai_edit_service: StorybookAIEditServiceDep,
    db: DBSession,
) -> AIRewriteResponse:
    """Rewrite storybook text content using the AI edit service."""
    if request.storybook_id != storybook_id:
        return AIRewriteResponse(
            success=False,
            error="Path storybook_id does not match request.storybook_id",
        )

    storybook = await service.get_storybook_detail(
        db,
        storybook_id=storybook_id,
        include_pages=False,
    )
    if not storybook:
        return AIRewriteResponse(success=False, error="Storybook not found")

    session_data = await session_service.get_session_details(
        db,
        storybook.session_id,
        current_user.id,
    )
    if not session_data:
        return AIRewriteResponse(
            success=False,
            error="Access denied to this storybook",
        )

    try:
        rewritten_text = await ai_edit_service.rewrite_content(
            db,
            storybook=storybook,
            user_id=current_user.id,
            content=request.content,
            page_image_url=request.page_image_url,
        )
        return AIRewriteResponse(success=True, rewritten_content=rewritten_text)
    except PaymentRequiredError:
        return AIRewriteResponse(success=False, error="Insufficient credits")
    except ValidationError as exc:
        return AIRewriteResponse(success=False, error=exc.message)
    except Exception as exc:
        logger.error("[Storybook AI Rewrite] Failed: %s", exc, exc_info=True)
        return AIRewriteResponse(
            success=False,
            error=f"Failed to rewrite content: {exc}",
        )


@router.post(
    "/{storybook_id}/edit/ai-generate-background",
    response_model=AIGenerateBackgroundResponse,
)
async def ai_generate_storybook_background(
    storybook_id: uuid.UUID,
    request: AIGenerateBackgroundRequest,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    session_service: SessionServiceDep,
    ai_edit_service: StorybookAIEditServiceDep,
    db: DBSession,
) -> AIGenerateBackgroundResponse:
    """Generate or outpaint a background image for storybook editing."""
    if request.storybook_id != storybook_id:
        return AIGenerateBackgroundResponse(
            success=False,
            error="Path storybook_id does not match request.storybook_id",
        )

    storybook = await service.get_storybook_detail(
        db,
        storybook_id=storybook_id,
        include_pages=False,
    )
    if not storybook:
        return AIGenerateBackgroundResponse(success=False, error="Storybook not found")

    session_data = await session_service.get_session_details(
        db,
        storybook.session_id,
        current_user.id,
    )
    if not session_data:
        return AIGenerateBackgroundResponse(
            success=False,
            error="Access denied to this storybook",
        )

    try:
        image_url = await ai_edit_service.generate_background(
            db,
            storybook=storybook,
            user_id=current_user.id,
            prompt=request.prompt,
            page_image_url=request.page_image_url,
            text_position=request.text_position,
        )
        return AIGenerateBackgroundResponse(success=True, image_url=image_url)
    except InsufficientCreditsError as exc:
        return AIGenerateBackgroundResponse(success=False, error=exc.message)
    except ValidationError as exc:
        return AIGenerateBackgroundResponse(success=False, error=exc.message)
    except Exception as exc:
        logger.error("[Storybook AI Background] Failed: %s", exc, exc_info=True)
        return AIGenerateBackgroundResponse(
            success=False,
            error=f"Failed to generate image: {exc}",
        )


@router.post(
    "/{storybook_id}/edit/ai-regenerate-image",
    response_model=AIRegenerateImageResponse,
)
async def ai_regenerate_storybook_image(
    storybook_id: uuid.UUID,
    request: AIRegenerateImageRequest,
    current_user: CurrentUser,
    service: StorybookServiceDep,
    session_service: SessionServiceDep,
    ai_edit_service: StorybookAIEditServiceDep,
    db: DBSession,
) -> AIRegenerateImageResponse:
    """Generate a replacement page image using storybook context and layout metadata."""
    if request.storybook_id != storybook_id:
        return AIRegenerateImageResponse(
            success=False,
            error="Path storybook_id does not match request.storybook_id",
        )

    storybook = await service.get_storybook_detail(
        db,
        storybook_id=storybook_id,
        include_pages=True,
    )
    if not storybook:
        return AIRegenerateImageResponse(success=False, error="Storybook not found")

    session_data = await session_service.get_session_details(
        db,
        storybook.session_id,
        current_user.id,
    )
    if not session_data:
        return AIRegenerateImageResponse(
            success=False,
            error="Access denied to this storybook",
        )

    try:
        image_url = await ai_edit_service.regenerate_image(
            db,
            storybook=storybook,
            user_id=current_user.id,
            page_number=request.page_number,
            prompt=request.prompt,
            reference_image_url=request.reference_image_url,
            scene_text=request.scene_text,
            text_position=request.text_position,
            text_percentage=request.text_percentage,
        )
        return AIRegenerateImageResponse(success=True, image_url=image_url)
    except InsufficientCreditsError as exc:
        return AIRegenerateImageResponse(success=False, error=exc.message)
    except ValidationError as exc:
        return AIRegenerateImageResponse(success=False, error=exc.message)
    except Exception as exc:
        logger.error("[Storybook AI Regenerate] Failed: %s", exc, exc_info=True)
        return AIRegenerateImageResponse(
            success=False,
            error=str(exc),
        )


@router.get("/{storybook_id}/download")
async def download_storybook(
    storybook_id: uuid.UUID,
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

    session_data = await session_service.get_session_details(
        db, storybook.session_id, current_user.id
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    pdf_bytes = await export_service.download_storybook_as_pdf(db, storybook_id)
    if not pdf_bytes:
        raise StorybookExportError("Failed to generate PDF")

    filename = f"{storybook.name.replace(' ', '_')}_{str(storybook_id)[:8]}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": _format_content_disposition(filename),
        },
    )


@router.get("/{storybook_id}/download/stream")
async def download_storybook_with_progress(
    storybook_id: uuid.UUID,
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

    session_data = await session_service.get_session_details(
        db, storybook.session_id, current_user.id
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
    storybook_id: uuid.UUID,
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

    session_data = await session_service.get_session_details(
        db, storybook.session_id, current_user.id
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    pdf_bytes = await export_service.download_storybook_page_as_pdf(db, storybook_id, page_number)
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
    storybook_id: uuid.UUID,
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

    session_data = await session_service.get_session_details(
        db, storybook.session_id, current_user.id
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    png_bytes = await export_service.download_storybook_page_as_png(db, storybook_id, page_number)
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
    storybook_id: uuid.UUID,
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

    session_data = await session_service.get_session_details(
        db, storybook.session_id, current_user.id
    )
    if not session_data:
        raise StorybookAccessDeniedError("Access denied to this storybook")

    zip_bytes = await export_service.download_storybook_as_png_zip(db, storybook_id)
    if not zip_bytes:
        raise StorybookExportError("Failed to generate PNG files")

    filename = f"{storybook.name.replace(' ', '_')}_{str(storybook_id)[:8]}-pages.zip"

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": _format_content_disposition(filename),
        },
    )


@router.get("/{storybook_id}/download/png/stream")
async def download_storybook_png_with_progress(
    storybook_id: uuid.UUID,
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

    session_data = await session_service.get_session_details(
        db, storybook.session_id, current_user.id
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


# ---------------------------------------------------------------------------
# Public endpoints (served under /v1/public/storybooks)
# ---------------------------------------------------------------------------

public_router = APIRouter(prefix="/storybooks", tags=["Storybooks Public"])


@public_router.get("/{storybook_id}", response_model=StorybookDetail)
async def get_public_storybook(
    storybook_id: uuid.UUID,
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

    session_data = await session_service.get_public_session_details(db, storybook.session_id)
    if not session_data:
        raise StorybookNotFoundError("Storybook not found or not public")

    return storybook
