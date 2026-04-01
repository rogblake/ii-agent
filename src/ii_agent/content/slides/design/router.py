"""Slide design mode API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.content.slides.design.dependencies import SlideDesignServiceDep
from ii_agent.content.slides.design.schemas import (
    SlideDeckSyncBatchRequest,
    SlideDeckSyncBatchResponse,
    SlideSyncBatchRequest,
    SlideSyncBatchResponse,
)

router = APIRouter(prefix="/design", tags=["Slide Design Mode"])

_HTML_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


@router.get("/slide-proxy", response_class=HTMLResponse)
async def slide_proxy_design_mode(
    current_user: CurrentUser,
    db: DBSession,
    service: SlideDesignServiceDep,
    session_id: str = Query(..., description="Session ID"),
    presentation_name: str = Query(..., description="Presentation name"),
    slide_number: int = Query(..., description="Slide number (1-based)"),
) -> HTMLResponse:
    html = await service.get_slide_proxy_html(
        db,
        session_id=session_id,
        user_id=str(current_user.id),
        presentation_name=presentation_name,
        slide_number=slide_number,
    )
    return HTMLResponse(content=html, headers=_HTML_HEADERS)


@router.get("/slide-deck-proxy", response_class=HTMLResponse)
async def slide_deck_proxy_design_mode(
    current_user: CurrentUser,
    db: DBSession,
    service: SlideDesignServiceDep,
    session_id: str = Query(..., description="Session ID"),
    presentation_name: str = Query(..., description="Presentation name"),
) -> HTMLResponse:
    html = await service.get_slide_deck_proxy_html(
        db,
        session_id=session_id,
        user_id=str(current_user.id),
        presentation_name=presentation_name,
    )
    return HTMLResponse(content=html, headers=_HTML_HEADERS)


@router.post("/slide-sync-batch", response_model=SlideSyncBatchResponse)
async def slide_sync_batch(
    request: SlideSyncBatchRequest,
    current_user: CurrentUser,
    db: DBSession,
    service: SlideDesignServiceDep,
) -> SlideSyncBatchResponse:
    return await service.apply_slide_sync_batch(
        db,
        request=request,
        user_id=str(current_user.id),
    )


@router.post("/slide-deck-sync-batch", response_model=SlideDeckSyncBatchResponse)
async def slide_deck_sync_batch(
    request: SlideDeckSyncBatchRequest,
    current_user: CurrentUser,
    db: DBSession,
    service: SlideDesignServiceDep,
) -> SlideDeckSyncBatchResponse:
    return await service.apply_slide_deck_sync_batch(
        db,
        request=request,
        user_id=str(current_user.id),
    )


