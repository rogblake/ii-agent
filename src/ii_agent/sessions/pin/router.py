"""Pin management API endpoints."""

import logging
from fastapi import APIRouter

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.sessions.pin.dependencies import PinServiceDep
from ii_agent.sessions.pin.schemas import (
    SessionPinResponse,
    SessionPinItem,
    PinActionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pin", tags=["Pin"])


@router.get("/sessions", response_model=SessionPinResponse)
async def get_pinned_sessions(
    current_user: CurrentUser,
    pin_service: PinServiceDep,
    db: DBSession,
) -> SessionPinResponse:
    """Get all pinned sessions for the current user."""
    sessions_data = await pin_service.get_user_pins(
        db, str(current_user.id)
    )

    sessions = [SessionPinItem(**session) for session in sessions_data]

    return SessionPinResponse(sessions=sessions, total=len(sessions))


@router.post("/sessions/{session_id}", response_model=PinActionResponse)
async def pin_session(
    session_id: str,
    current_user: CurrentUser,
    pin_service: PinServiceDep,
    db: DBSession,
) -> PinActionResponse:
    """Pin a session for the current user."""
    success = await pin_service.pin_session(
        db, str(current_user.id), session_id
    )

    if not success:
        return PinActionResponse(
            success=False,
            message="Session already pinned",
            session_id=session_id,
        )

    return PinActionResponse(
        success=True, message="Session pinned", session_id=session_id
    )


@router.delete("/sessions/{session_id}", response_model=PinActionResponse)
async def unpin_session(
    session_id: str,
    current_user: CurrentUser,
    pin_service: PinServiceDep,
    db: DBSession,
) -> PinActionResponse:
    """Unpin a session for the current user."""
    success = await pin_service.unpin_session(
        db, str(current_user.id), session_id
    )

    if not success:
        return PinActionResponse(
            success=False,
            message="Session not pinned",
            session_id=session_id,
        )

    return PinActionResponse(
        success=True, message="Session unpinned", session_id=session_id
    )
