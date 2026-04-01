"""Repository layer for credits domain — data access only."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import Numeric, cast, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db import BaseRepository
from ii_agent.credits.models import CreditBalance, CreditTransaction, CreditType
from ii_agent.sessions.models import Session


# ---------------------------------------------------------------------------
# CreditBalanceRepository
# ---------------------------------------------------------------------------


class CreditBalanceRepository(BaseRepository[CreditBalance]):
    model = CreditBalance

    async def get_by_user_id(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> Optional[CreditBalance]:
        result = await db.execute(
            select(CreditBalance).where(CreditBalance.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_for_update(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> Optional[CreditBalance]:
        """SELECT ... FOR UPDATE — serializes concurrent mutations."""
        result = await db.execute(
            select(CreditBalance)
            .where(CreditBalance.user_id == user_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# CreditTransactionRepository
# ---------------------------------------------------------------------------


class CreditTransactionRepository(BaseRepository[CreditTransaction]):
    model = CreditTransaction

    async def get_session_summaries(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        page: int,
        per_page: int,
    ) -> tuple[list[dict], int]:
        """Aggregate credit usage per session, joined with session title."""

        base_filter = (
            (CreditTransaction.user_id == user_id)
            & (CreditTransaction.session_id.is_not(None))
            & (CreditTransaction.amount < 0)  # Only deductions
        )

        # Count distinct sessions
        count_q = select(
            func.count(func.distinct(CreditTransaction.session_id))
        ).where(base_filter)
        total = (await db.execute(count_q)).scalar_one()

        # Aggregate per session
        updated_at_col = func.max(CreditTransaction.created_at).label("updated_at")

        # Sum regular deductions
        regular_sum = func.coalesce(
            func.sum(
                cast(CreditTransaction.amount, Numeric(18, 6))
            ).filter(CreditTransaction.credit_type == CreditType.REGULAR),
            0,
        ).label("credits")

        # Sum bonus deductions
        bonus_sum = func.coalesce(
            func.sum(
                cast(CreditTransaction.amount, Numeric(18, 6))
            ).filter(CreditTransaction.credit_type == CreditType.BONUS),
            0,
        ).label("bonus_credits")

        q = (
            select(
                CreditTransaction.session_id.label("session_id"),
                func.coalesce(Session.name, CreditTransaction.session_id).label(
                    "session_title"
                ),
                regular_sum,
                bonus_sum,
                updated_at_col,
            )
            .outerjoin(
                Session,
                Session.id == CreditTransaction.session_id,
            )
            .where(base_filter)
            .group_by(CreditTransaction.session_id, Session.name)
            .order_by(desc(updated_at_col))
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        rows = (await db.execute(q)).all()

        sessions = [
            {
                "session_id": str(row.session_id),
                "session_title": row.session_title or str(row.session_id),
                "credits": float(abs(row.credits)),  # Show as positive
                "bonus_credits": float(abs(row.bonus_credits)),
                "updated_at": row.updated_at,
            }
            for row in rows
        ]
        return sessions, total

    async def get_by_session(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        page: int,
        per_page: int,
    ) -> tuple[list[CreditTransaction], int]:
        """Paginated transactions for a specific session."""

        base_filter = (
            (CreditTransaction.user_id == user_id)
            & (CreditTransaction.session_id == session_id)
        )

        total = (
            await db.execute(
                select(func.count()).select_from(
                    select(CreditTransaction.id).where(base_filter).subquery()
                )
            )
        ).scalar_one()

        q = (
            select(CreditTransaction)
            .where(base_filter)
            .order_by(desc(CreditTransaction.created_at))
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        items = (await db.execute(q)).scalars().all()
        return list(items), total

    async def get_session_total_credits(
        self, db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
    ) -> Decimal:
        """Sum of all deductions in a session (returned as positive)."""
        q = select(
            func.coalesce(
                func.sum(cast(CreditTransaction.amount, Numeric(18, 6))), 0
            )
        ).where(
            (CreditTransaction.user_id == user_id)
            & (CreditTransaction.session_id == session_id)
            & (CreditTransaction.amount < 0)
        )
        result = (await db.execute(q)).scalar_one()
        return abs(result)

    async def get_by_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        page: int,
        per_page: int,
        transaction_type: Optional[str] = None,
    ) -> tuple[list[CreditTransaction], int]:
        """Paginated full transaction history for a user."""

        base_filter = CreditTransaction.user_id == user_id
        if transaction_type:
            base_filter = base_filter & (
                CreditTransaction.transaction_type == transaction_type
            )

        total = (
            await db.execute(
                select(func.count()).select_from(
                    select(CreditTransaction.id).where(base_filter).subquery()
                )
            )
        ).scalar_one()

        q = (
            select(CreditTransaction)
            .where(base_filter)
            .order_by(desc(CreditTransaction.created_at))
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        items = (await db.execute(q)).scalars().all()
        return list(items), total
