"""Credit management API endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.credits.dependencies import CreditServiceDep
from ii_agent.credits.schemas import (
    CreditBalanceResponse,
    CreditHistoryResponse,
    CreditUsageResponse,
    SessionUsageDetailResponse,
)

router = APIRouter(prefix="/credits", tags=["Credits"])


@router.get("/balance", response_model=CreditBalanceResponse)
async def get_credit_balance(
    db: DBSession,
    current_user: CurrentUser,
    credit_service: CreditServiceDep,
) -> CreditBalanceResponse:
    """Get the current user's credit balance."""
    balance = await credit_service.get_balance(db, current_user.id)
    if balance is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credit balance not found",
        )
    return balance


@router.get("/usage", response_model=CreditUsageResponse)
async def get_credit_usage(
    db: DBSession,
    current_user: CurrentUser,
    credit_service: CreditServiceDep,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> CreditUsageResponse:
    """Get credit usage aggregated by session."""
    return await credit_service.get_usage_by_session(
        db, current_user.id, page, per_page
    )


@router.get("/usage/{session_id}", response_model=SessionUsageDetailResponse)
async def get_session_usage_detail(
    session_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
    credit_service: CreditServiceDep,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
) -> SessionUsageDetailResponse:
    """Get detailed credit transactions for a specific session."""
    return await credit_service.get_session_usage_detail(
        db, current_user.id, session_id, page, per_page
    )


@router.get("/history", response_model=CreditHistoryResponse)
async def get_credit_history(
    db: DBSession,
    current_user: CurrentUser,
    credit_service: CreditServiceDep,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    transaction_type: str | None = Query(None),
) -> CreditHistoryResponse:
    """Get full paginated credit transaction history."""
    items, total = await credit_service.get_transaction_history(
        db,
        current_user.id,
        page,
        per_page,
        transaction_type=transaction_type,
    )
    return CreditHistoryResponse(
        transactions=items,
        total=total,
        page=page,
        per_page=per_page,
    )
