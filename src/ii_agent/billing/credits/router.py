"""Credit management API endpoints."""

from typing import Any
from fastapi import APIRouter, HTTPException, Query

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.billing.credits.dependencies import CreditServiceDep
from ii_agent.billing.credits.exceptions import CreditBalanceNotFoundError
from ii_agent.billing.credits.schemas import (
    CreditBalance,
    CreditHistory,
    CreditSubjectHistory,
    LedgerEntryResponse,
    LedgerHistory,
    ReservationHistory,
    ReservationResponse,
    SessionCreditHistory,
    SessionUsageDetail,
    SessionUsageItem,
    SubjectCreditHistory,
    SubjectUsageDetail,
)
from ii_agent.billing.reservations.dependencies import CreditReservationRepositoryDep
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


@router.get("/subjects/usage", response_model=CreditSubjectHistory)
async def get_credit_usage_by_subject(
    db: DBSession,
    current_user: CurrentUser,
    credit_service: CreditServiceDep,
    usage_service: UsageServiceDep,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
) -> Any:
    """Get the current user's credit usage grouped by billing subject."""
    credit_balance = await credit_service.get_balance(db, str(current_user.id))

    if not credit_balance:
        raise CreditBalanceNotFoundError("User credit balance not found")

    subject_history, total = await usage_service.get_subject_history(
        db,
        str(current_user.id),
        page=page,
        per_page=per_page,
    )

    return CreditSubjectHistory(
        subjects=[
            SubjectCreditHistory(
                subject_kind=subject["subject_kind"],
                subject_id=subject["subject_id"],
                subject_title=subject["subject_title"],
                credits=subject["credits"],
                updated_at=subject["updated_at"],
            )
            for subject in subject_history
        ],
        total=total,
    )


@router.get("/subjects/{subject_kind}/{subject_id}/usage", response_model=SubjectUsageDetail)
async def get_subject_usage_detail(
    subject_kind: str,
    subject_id: str,
    db: DBSession,
    current_user: CurrentUser,
    usage_service: UsageServiceDep,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
) -> Any:
    """Get detailed credit usage breakdown for a specific billing subject."""
    items, total, subject_title, total_credits = await usage_service.get_subject_usage_detail(
        db,
        str(current_user.id),
        subject_kind,
        subject_id,
        page=page,
        per_page=per_page,
    )

    if subject_title is None:
        raise HTTPException(status_code=404, detail="Billing subject not found")

    return SubjectUsageDetail(
        subject_kind=subject_kind,
        subject_id=subject_id,
        subject_title=subject_title,
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


@router.get("/subjects/{subject_kind}/{subject_id}/ledger", response_model=LedgerHistory)
async def get_subject_credit_ledger(
    subject_kind: str,
    subject_id: str,
    db: DBSession,
    current_user: CurrentUser,
    credit_service: CreditServiceDep,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
) -> Any:
    """Get credit ledger entries for a specific billing subject."""
    entries, total = await credit_service.get_subject_ledger_history(
        db,
        str(current_user.id),
        subject_kind,
        subject_id,
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


@router.get("/subjects/{subject_kind}/{subject_id}/reservations", response_model=ReservationHistory)
async def get_subject_reservations(
    subject_kind: str,
    subject_id: str,
    db: DBSession,
    current_user: CurrentUser,
    reservation_repo: CreditReservationRepositoryDep,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
) -> Any:
    """Get credit reservations for a specific billing subject."""
    entries, total = await reservation_repo.get_history_by_subject(
        db,
        str(current_user.id),
        subject_kind,
        subject_id,
        page=page,
        per_page=per_page,
    )

    return ReservationHistory(
        entries=[ReservationResponse.model_validate(e) for e in entries],
        total=total,
    )


@router.get("/reservations/{session_id}", response_model=ReservationHistory)
async def get_session_reservations(
    session_id: str,
    db: DBSession,
    current_user: CurrentUser,
    reservation_repo: CreditReservationRepositoryDep,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
) -> Any:
    """Get credit reservations for a specific session (developer view)."""

    entries, total = await reservation_repo.get_history_by_session(
        db,
        str(current_user.id),
        session_id,
        page=page,
        per_page=per_page,
    )

    return ReservationHistory(
        entries=[ReservationResponse.model_validate(e) for e in entries],
        total=total,
    )
