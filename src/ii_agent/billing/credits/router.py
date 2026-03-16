"""Credit management API endpoints."""

from typing import Any
from fastapi import APIRouter, HTTPException, Query

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.billing.credits.dependencies import CreditServiceDep
from ii_agent.billing.credits.exceptions import CreditBalanceNotFoundError
from ii_agent.billing.credits.schemas import (
    CreditBalance,
    CreditHistory,
    LedgerEntryResponse,
    LedgerHistory,
    SessionCreditHistory,
    SessionUsageDetail,
    SessionUsageItem,
)
from ii_agent.billing.usage.dependencies import UsageServiceDep

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
    usage_service: UsageServiceDep,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
) -> Any:
    """Get the current user's credit usage by session with pagination."""

    # Get current balance
    credit_balance = await credit_service.get_balance(db, str(current_user.id))

    if not credit_balance:
        raise CreditBalanceNotFoundError("User credit balance not found")

    # Get session-based credit history with pagination
    session_history, total = await usage_service.get_history(
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


@router.get("/usage/{session_id}", response_model=SessionUsageDetail)
async def get_session_usage_detail(
    session_id: str,
    db: DBSession,
    current_user: CurrentUser,
    usage_service: UsageServiceDep,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
) -> Any:
    """Get detailed credit usage breakdown for a specific session."""

    items, total, session_title, total_credits = await usage_service.get_session_usage_detail(
        db,
        str(current_user.id),
        session_id,
        page=page,
        per_page=per_page,
    )

    if not session_title:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionUsageDetail(
        session_id=session_id,
        session_title=session_title,
        items=[SessionUsageItem(**item) for item in items],
        total_credits=total_credits,
        total_items=total,
    )


@router.get("/ledger", response_model=LedgerHistory)
async def get_credit_ledger(
    db: DBSession,
    current_user: CurrentUser,
    credit_service: CreditServiceDep,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
) -> Any:
    """Get the current user's credit ledger history with pagination."""

    entries, total = await credit_service.get_ledger_history(
        db,
        str(current_user.id),
        page=page,
        per_page=per_page,
    )

    return LedgerHistory(
        entries=[LedgerEntryResponse.model_validate(e) for e in entries],
        total=total,
    )


@router.get("/ledger/{session_id}", response_model=LedgerHistory)
async def get_session_credit_ledger(
    session_id: str,
    db: DBSession,
    current_user: CurrentUser,
    credit_service: CreditServiceDep,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
) -> Any:
    """Get credit ledger entries for a specific session (developer view)."""

    entries, total = await credit_service.get_session_ledger_history(
        db,
        str(current_user.id),
        session_id,
        page=page,
        per_page=per_page,
    )

    return LedgerHistory(
        entries=[LedgerEntryResponse.model_validate(e) for e in entries],
        total=total,
    )
