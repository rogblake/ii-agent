"""Repository layer for credit ledger entries."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.credits.ledger_models import CreditLedgerEntry

logger = logging.getLogger(__name__)


class CreditLedgerRepository:
    """Data access layer for CreditLedgerEntry model."""

    async def append(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        entry_type: str,
        source_domain: Optional[str] = None,
        source_id: Optional[str] = None,
        delta_credits: Decimal | float = Decimal("0"),
        delta_bonus_credits: Decimal | float = Decimal("0"),
        balance_after_credits: Optional[Decimal] = None,
        balance_after_bonus_credits: Optional[Decimal] = None,
        entry_metadata: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
    ) -> CreditLedgerEntry | None:
        """Append a new entry to the credit ledger.

        Only deltas are recorded.  Current balances live in
        ``credit_balances``; historical balances can be derived by
        summing deltas.

        When *idempotency_key* is provided the insert uses
        ``INSERT … ON CONFLICT DO NOTHING`` on the unique constraint so
        duplicate calls are silently ignored.  Returns ``None`` when the
        entry already existed.
        """
        if idempotency_key is not None:
            return await self._append_idempotent(
                db,
                user_id=user_id,
                entry_type=entry_type,
                source_domain=source_domain,
                source_id=source_id,
                delta_credits=delta_credits,
                delta_bonus_credits=delta_bonus_credits,
                balance_after_credits=balance_after_credits,
                balance_after_bonus_credits=balance_after_bonus_credits,
                entry_metadata=entry_metadata,
                idempotency_key=idempotency_key,
            )

        entry = CreditLedgerEntry(
            user_id=user_id,
            entry_type=entry_type,
            source_domain=source_domain,
            source_id=source_id,
            delta_credits=Decimal(str(delta_credits)),
            delta_bonus_credits=Decimal(str(delta_bonus_credits)),
            balance_after_credits=balance_after_credits,
            balance_after_bonus_credits=balance_after_bonus_credits,
            entry_metadata=entry_metadata,
        )
        db.add(entry)
        await db.flush()
        return entry

    async def _append_idempotent(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        entry_type: str,
        source_domain: Optional[str],
        source_id: Optional[str],
        delta_credits: Decimal | float,
        delta_bonus_credits: Decimal | float,
        balance_after_credits: Optional[Decimal],
        balance_after_bonus_credits: Optional[Decimal],
        entry_metadata: Optional[dict],
        idempotency_key: str,
    ) -> CreditLedgerEntry | None:
        """Insert with ``ON CONFLICT DO NOTHING`` on *idempotency_key*."""
        from datetime import datetime, timezone

        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = (
            pg_insert(CreditLedgerEntry)
            .values(
                user_id=user_id,
                entry_type=entry_type,
                source_domain=source_domain,
                source_id=source_id,
                delta_credits=Decimal(str(delta_credits)),
                delta_bonus_credits=Decimal(str(delta_bonus_credits)),
                balance_after_credits=balance_after_credits,
                balance_after_bonus_credits=balance_after_bonus_credits,
                entry_metadata=entry_metadata,
                idempotency_key=idempotency_key,
                created_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_nothing(
                index_elements=[CreditLedgerEntry.idempotency_key],
                index_where=CreditLedgerEntry.idempotency_key.isnot(None),
            )
            .returning(CreditLedgerEntry.id)
        )
        result = await db.execute(stmt)
        await db.flush()
        row = result.first()
        if row is None:
            logger.info(
                "Duplicate ledger entry skipped (idempotency_key=%s)", idempotency_key
            )
            return None
        # Fetch the full entry for callers that need it
        full = await db.execute(
            select(CreditLedgerEntry).where(CreditLedgerEntry.id == row.id)
        )
        return full.scalar_one()

    async def get_balance(
        self, db: AsyncSession, user_id: str
    ) -> tuple[Decimal, Decimal]:
        """Compute balance from ledger by summing deltas (reconciliation only).

        Always returns a ``(credits, bonus_credits)`` tuple.  Users with no
        ledger entries return ``(0, 0)`` thanks to ``COALESCE``.
        """
        result = await db.execute(
            select(
                func.coalesce(func.sum(CreditLedgerEntry.delta_credits), 0),
                func.coalesce(func.sum(CreditLedgerEntry.delta_bonus_credits), 0),
            ).where(CreditLedgerEntry.user_id == user_id)
        )
        row = result.one()
        return (Decimal(str(row[0])), Decimal(str(row[1])))

    async def get_history(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[CreditLedgerEntry], int]:
        """Get paginated credit ledger history for a user."""
        count_result = await db.execute(
            select(func.count()).where(CreditLedgerEntry.user_id == user_id)
        )
        total = count_result.scalar() or 0

        offset = (page - 1) * per_page
        result = await db.execute(
            select(CreditLedgerEntry)
            .where(CreditLedgerEntry.user_id == user_id)
            .order_by(CreditLedgerEntry.created_at.desc())
            .limit(per_page)
            .offset(offset)
        )
        entries = list(result.scalars().all())
        return entries, total

    async def get_history_by_session(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
        *,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[CreditLedgerEntry], int]:
        """Get paginated credit ledger entries for a specific session."""
        base_where = (
            (CreditLedgerEntry.user_id == user_id)
            & (CreditLedgerEntry.source_id == session_id)
        )

        count_result = await db.execute(
            select(func.count()).where(base_where)
        )
        total = count_result.scalar() or 0

        offset = (page - 1) * per_page
        result = await db.execute(
            select(CreditLedgerEntry)
            .where(base_where)
            .order_by(CreditLedgerEntry.created_at.asc())
            .limit(per_page)
            .offset(offset)
        )
        entries = list(result.scalars().all())
        return entries, total
