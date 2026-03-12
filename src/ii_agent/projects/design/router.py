"""Project design mode API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.projects.design.dependencies import ProjectDesignServiceDep
from ii_agent.projects.design.schemas import (
    AIChangeRequest,
    AIChangeResponse,
    DesignStateRequest,
    DesignStateResponse,
    IframeAIPlanRequest,
    IframeAIPlanResponse,
)

router = APIRouter(prefix="/projects/design", tags=["Project Design Mode"])

_HTML_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


@router.get("/proxy", response_class=HTMLResponse)
async def proxy_design_mode(
    current_user: CurrentUser,
    db: DBSession,
    service: ProjectDesignServiceDep,
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
    service: ProjectDesignServiceDep,
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
    service: ProjectDesignServiceDep,
) -> IframeAIPlanResponse:
    return await service.ai_iframe_plan(
        db,
        user_id=str(current_user.id),
        request=request,
    )


@router.get("/state", response_model=DesignStateResponse)
async def get_design_state(
    session_id: str,
    current_user: CurrentUser,
    db: DBSession,
    service: ProjectDesignServiceDep,
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
    service: ProjectDesignServiceDep,
) -> DesignStateResponse:
    return await service.save_design_state(
        db,
        request=request,
        user_id=str(current_user.id),
    )


