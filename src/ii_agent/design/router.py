"""Design mode API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.design.dependencies import DesignServiceDep
from ii_agent.design.schemas import (
    AIChangeRequest,
    AIChangeResponse,
    DesignStateRequest,
    DesignStateResponse,
    IframeAIPlanRequest,
    IframeAIPlanResponse,
    SlideDeckSyncBatchRequest,
    SlideDeckSyncBatchResponse,
    SlideDeckSyncStateRequest,
    SlideDeckSyncStateResponse,
    SlideSyncBatchRequest,
    SlideSyncBatchResponse,
    SyncRequest,
    SyncResponse,
    SyncStateRequest,
    SyncStateResponse,
)

router = APIRouter(prefix="/design-mode", tags=["Design Mode"])

_HTML_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


@router.get("/proxy", response_class=HTMLResponse)
async def proxy_design_mode(
    current_user: CurrentUser,
    db: DBSession,
    service: DesignServiceDep,
    session_id: str = Query(..., description="Session ID"),
    url: str = Query(..., description="Sandbox URL to proxy"),
) -> HTMLResponse:
    html = await service.get_proxy_html(
        db,
        session_id=session_id,
        user_id=str(current_user.id),
        url=url,
    )
    return HTMLResponse(
        content=html,
        headers={
            **_HTML_HEADERS,
            "Content-Security-Policy": "sandbox allow-scripts allow-forms allow-popups",
        },
    )


@router.post("/ai-change", response_model=AIChangeResponse)
async def ai_change(
    request: AIChangeRequest,
    current_user: CurrentUser,
    db: DBSession,
    service: DesignServiceDep,
) -> AIChangeResponse:
    return await service.ai_design_change(
        db,
        user_id=str(current_user.id),
        request=request,
    )


@router.post("/ai-iframe-plan", response_model=IframeAIPlanResponse)
async def ai_iframe_plan(
    request: IframeAIPlanRequest,
    current_user: CurrentUser,
    db: DBSession,
    service: DesignServiceDep,
) -> IframeAIPlanResponse:
    return await service.ai_iframe_plan(
        db,
        user_id=str(current_user.id),
        request=request,
    )


@router.get("/slide-proxy", response_class=HTMLResponse)
async def slide_proxy_design_mode(
    current_user: CurrentUser,
    db: DBSession,
    service: DesignServiceDep,
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
    service: DesignServiceDep,
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
    service: DesignServiceDep,
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
    service: DesignServiceDep,
) -> SlideDeckSyncBatchResponse:
    return await service.apply_slide_deck_sync_batch(
        db,
        request=request,
        user_id=str(current_user.id),
    )


@router.get("/state", response_model=DesignStateResponse)
async def get_design_state(
    session_id: str,
    current_user: CurrentUser,
    db: DBSession,
    service: DesignServiceDep,
) -> DesignStateResponse:
    return await service.get_design_state(
        db,
        session_id=session_id,
        user_id=str(current_user.id),
    )


@router.post("/state", response_model=DesignStateResponse)
async def save_design_state(
    request: DesignStateRequest,
    current_user: CurrentUser,
    db: DBSession,
    service: DesignServiceDep,
) -> DesignStateResponse:
    return await service.save_design_state(
        db,
        request=request,
        user_id=str(current_user.id),
    )


@router.post("/sync", response_model=SyncResponse)
async def sync_design_changes(
    request: SyncRequest,
    current_user: CurrentUser,
    db: DBSession,
    service: DesignServiceDep,
) -> SyncResponse:
    return await service.sync_design_changes(
        db,
        user_id=str(current_user.id),
        request=request,
    )


@router.post("/sync-state", response_model=SyncStateResponse)
async def sync_persisted_design_changes(
    request: SyncStateRequest,
    current_user: CurrentUser,
    db: DBSession,
    service: DesignServiceDep,
) -> SyncStateResponse:
    return await service.sync_persisted_design_changes(
        db,
        user_id=str(current_user.id),
        request=request,
    )


@router.post("/slide-deck-sync-state", response_model=SlideDeckSyncStateResponse)
async def sync_persisted_slide_deck_changes(
    request: SlideDeckSyncStateRequest,
    current_user: CurrentUser,
    db: DBSession,
    service: DesignServiceDep,
) -> SlideDeckSyncStateResponse:
    return await service.sync_persisted_slide_deck_changes(
        db,
        request=request,
        user_id=str(current_user.id),
    )
