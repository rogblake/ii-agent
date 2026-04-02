"""Credit management API endpoints."""

from typing import Any
from fastapi import APIRouter, Query

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.billing.credits.dependencies import CreditServiceDep
from ii_agent.billing.credits.exceptions import CreditBalanceNotFoundError
from ii_agent.billing.credits.schemas import CreditBalance, CreditHistory, SessionCreditHistory

router = APIRouter(prefix="/credits", tags=["Credits"])


@router.get("/balance", response_model=CreditBalance)
async def get_credit_balance(
    db: DBSession,
    current_user: CurrentUser,
    credit_service: CreditServiceDep,
) -> Any:
    """Get the current user's credit balance."""

    credit_balance = await credit_service.get_balance(db, str(current_user.id))

    if not credit_balance:
        raise CreditBalanceNotFoundError("User credit balance not found")

    return credit_balance


@router.get("/usage", response_model=CreditHistory)
async def get_credit_usage(
    db: DBSession,
    current_user: CurrentUser,
    credit_service: CreditServiceDep,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
) -> Any:
    """Get the current user's credit usage by session with pagination."""

    # Get current balance
    credit_balance = await credit_service.get_balance(db, str(current_user.id))

    if not credit_balance:
        raise CreditBalanceNotFoundError("User credit balance not found")

    # Get session-based credit history with pagination
    session_history, total = await credit_service.get_history(
        db,
        str(current_user.id),
        page=page,
        per_page=per_page,
    )

    # Convert to Pydantic models
    sessions = [
        SessionCreditHistory(
            session_id=session["session_id"],
            session_title=session["session_title"],
            credits=session["credits"],
            updated_at=session["updated_at"],
        )
        for session in session_history
    ]

    return CreditHistory(
        sessions=sessions,
        total=total,
    )
