"""Repository layer for prepaid credit reservations."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.reservations.models import CreditReservation
from ii_agent.billing.reservations.types import (
    ReservationStatus,
    SETTLEMENT_ERROR_SHORTFALL_UNRECONCILED,
)


class CreditReservationRepository:
    """Data access layer for ``credit_reservations``."""

    @staticmethod
    def _replayable_shortfall_filters(*, user_id: str | None = None) -> Sequence[object]:
        filters: list[object] = [
            CreditReservation.status == ReservationStatus.SETTLEMENT_FAILED,
            CreditReservation.last_error == SETTLEMENT_ERROR_SHORTFALL_UNRECONCILED,
        ]
        if user_id is not None:
            filters.insert(0, CreditReservation.user_id == user_id)
        return tuple(filters)

    async def get_by_idempotency_key(
        self, db: AsyncSession, idempotency_key: str
    ) -> CreditReservation | None:
        result = await db.execute(
            select(CreditReservation).where(CreditReservation.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, db: AsyncSession, reservation_id: str) -> CreditReservation | None:
        result = await db.execute(
            select(CreditReservation).where(CreditReservation.id == reservation_id)
        )
        return result.scalar_one_or_none()

    async def lock_by_id(self, db: AsyncSession, reservation_id: str) -> CreditReservation | None:
        result = await db.execute(
            select(CreditReservation)
            .where(CreditReservation.id == reservation_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_stale_reserved(
        self,
        db: AsyncSession,
        *,
        older_than: datetime,
        limit: int = 100,
    ) -> list[CreditReservation]:
        result = await db.execute(
            select(CreditReservation)
            .where(
                CreditReservation.status == ReservationStatus.RESERVED,
                CreditReservation.expires_at.isnot(None),
                CreditReservation.expires_at < older_than,
            )
            .order_by(CreditReservation.expires_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_settlement_failed(
        self,
        db: AsyncSession,
        *,
        limit: int = 50,
    ) -> list[CreditReservation]:
        """Return reservations stuck in ``settlement_failed``."""
        result = await db.execute(
            select(CreditReservation)
            .where(
                CreditReservation.status == ReservationStatus.SETTLEMENT_FAILED,
            )
            .order_by(CreditReservation.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_replayable_shortfall_failures(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        limit: int = 50,
    ) -> list[CreditReservation]:
        """Return shortfall-driven settlement failures eligible for payment-time replay."""
        result = await db.execute(
            select(CreditReservation)
            .where(*self._replayable_shortfall_filters(user_id=user_id))
            .order_by(CreditReservation.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_replayable_shortfall_failures_batch(
        self,
        db: AsyncSession,
        *,
        limit: int = 50,
    ) -> list[CreditReservation]:
        """Return replayable shortfall failures across all users."""
        result = await db.execute(
            select(CreditReservation)
            .where(*self._replayable_shortfall_filters())
            .order_by(CreditReservation.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def has_replayable_shortfall_failures(
        self,
        db: AsyncSession,
        *,
        user_id: str,
    ) -> bool:
        """Return whether a user still has replayable shortfall failures."""
        result = await db.execute(
            select(CreditReservation.id)
            .where(*self._replayable_shortfall_filters(user_id=user_id))
            .limit(1)
        )
        return result.first() is not None

    async def has_blocking_settlement_failures(
        self,
        db: AsyncSession,
        *,
        user_id: str,
    ) -> bool:
        """Return whether a user still has unresolved settlement failures."""
        result = await db.execute(
            select(CreditReservation.id)
            .where(
                CreditReservation.user_id == user_id,
                CreditReservation.status == ReservationStatus.SETTLEMENT_FAILED,
            )
            .limit(1)
        )
        return result.first() is not None

    async def get_outstanding_hold_totals(
        self,
        db: AsyncSession,
        *,
        user_id: str,
    ) -> tuple[Decimal, Decimal]:
        """Return unresolved held credits still missing from the spendable balance."""
        result = await db.execute(
            select(
                func.coalesce(
                    func.sum(
                        CreditReservation.reserved_credits
                        - func.coalesce(CreditReservation.released_credits, 0)
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        CreditReservation.reserved_bonus_credits
                        - func.coalesce(CreditReservation.released_bonus_credits, 0)
                    ),
                    0,
                ),
            ).where(
                CreditReservation.user_id == user_id,
                CreditReservation.status.in_(
                    (
                        ReservationStatus.RESERVED,
                        ReservationStatus.SETTLEMENT_FAILED,
                    )
                ),
            )
        )
        row = result.one()
        return (Decimal(str(row[0])), Decimal(str(row[1])))

    async def get_history_by_session(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
        *,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[CreditReservation], int]:
        """Get paginated reservations for a specific session."""
        return await self.get_history_by_subject(
            db,
            user_id=user_id,
            subject_kind="session",
            subject_id=session_id,
            page=page,
            per_page=per_page,
        )

    async def get_history_by_subject(
        self,
        db: AsyncSession,
        user_id: str,
        subject_kind: str,
        subject_id: str,
        *,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[CreditReservation], int]:
        """Get paginated reservations for a specific billing subject."""
        base_where = (
            (CreditReservation.user_id == user_id)
            & (CreditReservation.subject_kind == subject_kind)
            & (CreditReservation.subject_id == subject_id)
        )

        count_result = await db.execute(select(func.count()).where(base_where))
        total = count_result.scalar() or 0

        offset = (page - 1) * per_page
        result = await db.execute(
            select(CreditReservation)
            .where(base_where)
            .order_by(CreditReservation.created_at.asc())
            .limit(per_page)
            .offset(offset)
        )
        entries = list(result.scalars().all())
        return entries, total

    async def create(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        billing_context: str = "unknown",
        source_domain: str,
        source_id: str,
        billing_kind: str,
        quote_strategy: str,
        status: str,
        reserved_credits: Decimal,
        reserved_bonus_credits: Decimal,
        quoted_usd: Decimal,
        max_usd: Decimal,
        subject_kind: str,
        subject_id: str | None = None,
        run_id: UUID | str | None = None,
        model_id: str | None = None,
        tool_name: str | None = None,
        idempotency_key: str | None = None,
        reserve_ledger_entry_id: int | None = None,
        reservation_metadata: dict | None = None,
        expires_at: datetime | None = None,
    ) -> CreditReservation:
        reservation = CreditReservation(
            user_id=user_id,
            billing_context=billing_context,
            subject_kind=subject_kind,
            subject_id=subject_id,
            run_id=_coerce_uuid(run_id),
            source_domain=source_domain,
            source_id=source_id,
            billing_kind=billing_kind,
            quote_strategy=quote_strategy,
            status=status,
            model_id=model_id,
            tool_name=tool_name,
            idempotency_key=idempotency_key,
            reserve_ledger_entry_id=reserve_ledger_entry_id,
            reserved_credits=reserved_credits,
            reserved_bonus_credits=reserved_bonus_credits,
            quoted_usd=quoted_usd,
            max_usd=max_usd,
            reservation_metadata=reservation_metadata,
            expires_at=expires_at,
        )
        db.add(reservation)
        await db.flush()
        return reservation


def _coerce_uuid(value: UUID | str | None) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None
