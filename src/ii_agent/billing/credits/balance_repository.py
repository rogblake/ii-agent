"""Repository layer for credit_balances table."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.credits.balance_models import BillingStatus, CreditBalanceRecord


class CreditBalanceRepository:
    """Data access layer for the ``credit_balances`` table.

    All balance mutations use atomic SQL (UPDATE … RETURNING) to prevent
    race conditions — the same pattern previously used on the ``users`` table.

    All public methods accept and return ``Decimal`` for credit amounts to
    avoid float precision loss.  Conversion to ``float`` should only happen
    at the API boundary (schemas / DTOs).
    """

    async def get_balance(self, db: AsyncSession, user_id: str) -> tuple[Decimal, Decimal] | None:
        """Return ``(credits, bonus_credits)`` or ``None`` if no row exists."""
        result = await db.execute(
            select(CreditBalanceRecord.credits, CreditBalanceRecord.bonus_credits).where(
                CreditBalanceRecord.user_id == user_id
            )
        )
        row = result.first()
        if row is None:
            return None
        return (row.credits, row.bonus_credits)

    async def get_balance_state(
        self, db: AsyncSession, user_id: str
    ) -> tuple[Decimal, Decimal, str] | None:
        """Return ``(credits, bonus_credits, billing_status)`` or ``None``."""
        result = await db.execute(
            select(
                CreditBalanceRecord.credits,
                CreditBalanceRecord.bonus_credits,
                CreditBalanceRecord.billing_status,
            ).where(CreditBalanceRecord.user_id == user_id)
        )
        row = result.first()
        if row is None:
            return None
        return (row.credits, row.bonus_credits, row.billing_status)

    async def get_billing_status(self, db: AsyncSession, user_id: str) -> str | None:
        """Return the account billing status or ``None`` if no row exists."""
        result = await db.execute(
            select(CreditBalanceRecord.billing_status).where(CreditBalanceRecord.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_balance_with_updated_at(
        self, db: AsyncSession, user_id: str
    ) -> tuple[Decimal, Decimal, datetime] | None:
        """Return ``(credits, bonus_credits, updated_at)`` or ``None``."""
        result = await db.execute(
            select(
                CreditBalanceRecord.credits,
                CreditBalanceRecord.bonus_credits,
                CreditBalanceRecord.updated_at,
            ).where(CreditBalanceRecord.user_id == user_id)
        )
        row = result.first()
        if row is None:
            return None
        return (row.credits, row.bonus_credits, row.updated_at)

    async def check_sufficient(self, db: AsyncSession, user_id: str, amount: Decimal) -> bool:
        """Return ``True`` if the user has at least *amount* total credits.

        Single-column fetch — avoids deserializing the full balance row.
        """
        result = await db.execute(
            select(
                (CreditBalanceRecord.credits + CreditBalanceRecord.bonus_credits >= amount)
            ).where(CreditBalanceRecord.user_id == user_id)
        )
        row = result.scalar()
        return bool(row) if row is not None else False

    async def create(
        self,
        db: AsyncSession,
        user_id: str,
        credits: Decimal | float = Decimal("0"),
        bonus_credits: Decimal | float = Decimal("0"),
    ) -> CreditBalanceRecord:
        """Insert a new credit_balances row."""
        record = CreditBalanceRecord(
            user_id=user_id,
            credits=Decimal(str(credits)),
            bonus_credits=Decimal(str(bonus_credits)),
        )
        db.add(record)
        await db.flush()
        return record

    async def get_or_create(
        self,
        db: AsyncSession,
        user_id: str,
        credits: Decimal | float = Decimal("0"),
        bonus_credits: Decimal | float = Decimal("0"),
    ) -> tuple[Decimal, Decimal, bool]:
        """Return existing balance or create a new row atomically.

        Uses ``INSERT ... ON CONFLICT DO NOTHING`` (PostgreSQL) to avoid
        UNIQUE violations under concurrent requests.

        Returns ``(credits, bonus_credits, created)`` where *created* is
        ``True`` only when this call actually inserted the row.
        """
        existing = await self.get_balance(db, user_id)
        if existing is not None:
            return (existing[0], existing[1], False)

        import uuid
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = (
            pg_insert(CreditBalanceRecord)
            .values(
                id=str(uuid.uuid4()),
                user_id=user_id,
                credits=Decimal(str(credits)),
                bonus_credits=Decimal(str(bonus_credits)),
            )
            .on_conflict_do_nothing(index_elements=["user_id"])
            .returning(CreditBalanceRecord.user_id)
        )
        result = await db.execute(stmt)
        await db.flush()
        created = result.first() is not None
        balance = await self.get_balance(db, user_id)
        bal = balance or (Decimal(str(credits)), Decimal(str(bonus_credits)))
        return (bal[0], bal[1], created)

    async def lock_balance(self, db: AsyncSession, user_id: str) -> tuple[Decimal, Decimal] | None:
        """Lock and return ``(credits, bonus_credits)`` with ``FOR UPDATE``.

        Used to hold the row lock across multiple operations within a
        SAVEPOINT (e.g. ledger append then balance mutation).
        Returns ``None`` if no row exists.
        """
        CB = CreditBalanceRecord
        result = await db.execute(
            select(CB.credits, CB.bonus_credits).where(CB.user_id == user_id).with_for_update()
        )
        row = result.first()
        if row is None:
            return None
        return (row.credits, row.bonus_credits)

    async def lock_balance_state(
        self, db: AsyncSession, user_id: str
    ) -> tuple[Decimal, Decimal, str] | None:
        """Lock and return ``(credits, bonus_credits, billing_status)``."""
        CB = CreditBalanceRecord
        result = await db.execute(
            select(CB.credits, CB.bonus_credits, CB.billing_status)
            .where(CB.user_id == user_id)
            .with_for_update()
        )
        row = result.first()
        if row is None:
            return None
        return (row.credits, row.bonus_credits, row.billing_status)

    async def set_billing_status(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        billing_status: BillingStatus,
        billing_status_reason: str | None = None,
        expected_current_status: BillingStatus | None = None,
    ) -> bool:
        """Update only the billing status fields without a prior ``FOR UPDATE`` read."""
        CB = CreditBalanceRecord
        now = datetime.now(timezone.utc)
        where_clauses = [CB.user_id == user_id]
        if expected_current_status is not None:
            where_clauses.append(CB.billing_status == expected_current_status)

        result = await db.execute(
            update(CB)
            .where(*where_clauses)
            .values(
                billing_status=billing_status,
                billing_status_reason=billing_status_reason,
                billing_status_updated_at=now,
                updated_at=now,
            )
            .returning(CB.user_id)
        )
        return result.first() is not None

    async def apply_delta_locked(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        delta_credits: Decimal,
        delta_bonus_credits: Decimal,
        billing_status: BillingStatus | None = None,
        billing_status_reason: str | None = None,
    ) -> tuple[Decimal, Decimal, str] | None:
        """Apply exact bucket deltas while the caller holds the row lock."""
        CB = CreditBalanceRecord
        values: dict[str, Any] = {
            "credits": CB.credits + delta_credits,
            "bonus_credits": CB.bonus_credits + delta_bonus_credits,
            "updated_at": datetime.now(timezone.utc),
        }
        if billing_status is not None:
            values["billing_status"] = billing_status
            values["billing_status_reason"] = billing_status_reason
            values["billing_status_updated_at"] = datetime.now(timezone.utc)

        result = await db.execute(
            update(CB)
            .where(
                CB.user_id == user_id,
                CB.credits + delta_credits >= 0,
                CB.bonus_credits + delta_bonus_credits >= 0,
            )
            .values(**values)
            .returning(CB.credits, CB.bonus_credits, CB.billing_status)
        )
        row = result.first()
        if row is None:
            return None
        return (row.credits, row.bonus_credits, row.billing_status)

    async def _set_credits_locked(
        self,
        db: AsyncSession,
        user_id: str,
        amount: Decimal,
        *,
        bonus_amount: Decimal | None = None,
    ) -> tuple[Decimal, Decimal] | None:
        """Set exact balances while the caller already holds the row lock."""
        CB = CreditBalanceRecord

        values: dict[str, Any] = {
            "credits": amount,
            "updated_at": datetime.now(timezone.utc),
        }
        if bonus_amount is not None:
            values["bonus_credits"] = Decimal(str(bonus_amount))

        result = await db.execute(
            update(CB)
            .where(CB.user_id == user_id)
            .values(**values)
            .returning(CB.credits, CB.bonus_credits)
        )
        row = result.first()
        if row is None:
            return None
        return row.credits, row.bonus_credits
