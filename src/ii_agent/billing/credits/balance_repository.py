"""Repository layer for credit_balances table."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import case, select, update
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

    async def get_balance(
        self, db: AsyncSession, user_id: str
    ) -> tuple[Decimal, Decimal] | None:
        """Return ``(credits, bonus_credits)`` or ``None`` if no row exists."""
        result = await db.execute(
            select(CreditBalanceRecord.credits, CreditBalanceRecord.bonus_credits)
            .where(CreditBalanceRecord.user_id == user_id)
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

    async def get_billing_status(
        self, db: AsyncSession, user_id: str
    ) -> str | None:
        """Return the account billing status or ``None`` if no row exists."""
        result = await db.execute(
            select(CreditBalanceRecord.billing_status).where(
                CreditBalanceRecord.user_id == user_id
            )
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

    async def check_sufficient(
        self, db: AsyncSession, user_id: str, amount: Decimal
    ) -> bool:
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

    async def lock_balance(
        self, db: AsyncSession, user_id: str
    ) -> tuple[Decimal, Decimal] | None:
        """Lock and return ``(credits, bonus_credits)`` with ``FOR UPDATE``.

        Used to hold the row lock across multiple operations within a
        SAVEPOINT (e.g. ledger append then balance mutation).
        Returns ``None`` if no row exists.
        """
        CB = CreditBalanceRecord
        result = await db.execute(
            select(CB.credits, CB.bonus_credits)
            .where(CB.user_id == user_id)
            .with_for_update()
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

    async def deduct_credits(
        self, db: AsyncSession, user_id: str, amount: Decimal
    ) -> tuple[Decimal, Decimal, Decimal, Decimal] | None:
        """Atomically deduct credits (bonus first, then regular).

        Locks the row with ``FOR UPDATE``, then applies the deduction.
        Returns ``(old_credits, old_bonus, new_credits, new_bonus)`` after
        deduction, or ``None`` if the row was not found or had insufficient balance.
        """
        CB = CreditBalanceRecord
        amount = Decimal(str(amount))

        # Lock and read old values
        old_result = await db.execute(
            select(CB.credits, CB.bonus_credits)
            .where(CB.user_id == user_id)
            .with_for_update()
        )
        old_row = old_result.first()
        if old_row is None:
            return None
        old_credits: Decimal = old_row.credits
        old_bonus: Decimal = old_row.bonus_credits

        # Check sufficient balance using Decimal arithmetic
        if (old_credits + old_bonus) < amount:
            return None

        new_values = await self._apply_deduction(db, user_id, amount)
        if new_values is None:
            return None
        return (old_credits, old_bonus, new_values[0], new_values[1])

    async def _apply_deduction(
        self, db: AsyncSession, user_id: str, amount: Decimal
    ) -> tuple[Decimal, Decimal] | None:
        """Apply bonus-first deduction via UPDATE … RETURNING.

        Caller must already hold the ``FOR UPDATE`` row lock.
        Returns ``(new_credits, new_bonus)``
        or ``None`` if the row was not found.
        """
        CB = CreditBalanceRecord

        result = await db.execute(
            update(CB)
            .where(CB.user_id == user_id)
            .values(
                bonus_credits=case(
                    (CB.bonus_credits >= amount, CB.bonus_credits - amount),
                    else_=Decimal("0"),
                ),
                credits=case(
                    (CB.bonus_credits >= amount, CB.credits),
                    else_=CB.credits - (amount - CB.bonus_credits),
                ),
                updated_at=datetime.now(timezone.utc),
            )
            .returning(CB.credits, CB.bonus_credits)
        )
        row = result.first()
        if row is None:
            return None
        # Read pre-update values from the CASE expressions isn't possible
        # with RETURNING, so we rely on the caller having read them already.
        # Return new values only; the caller pairs them with the old values.
        return row.credits, row.bonus_credits

    async def add_credits(
        self,
        db: AsyncSession,
        user_id: str,
        amount: Decimal,
        *,
        is_bonus: bool = False,
    ) -> tuple[Decimal, Decimal, Decimal, Decimal] | None:
        """Atomically add credits to a user.

        Locks the row with ``FOR UPDATE`` to capture old values for accurate
        delta computation.  Returns ``(old_credits, old_bonus, new_credits,
        new_bonus)`` after addition, or ``None`` if the row was not found.
        """
        CB = CreditBalanceRecord
        amount = Decimal(str(amount))

        # Lock and read old values
        old_result = await db.execute(
            select(CB.credits, CB.bonus_credits)
            .where(CB.user_id == user_id)
            .with_for_update()
        )
        old_row = old_result.first()
        if old_row is None:
            return None
        old_credits: Decimal = old_row.credits
        old_bonus: Decimal = old_row.bonus_credits

        if is_bonus:
            values: dict[str, Any] = {
                "bonus_credits": CB.bonus_credits + amount,
                "updated_at": datetime.now(timezone.utc),
            }
        else:
            values = {
                "credits": CB.credits + amount,
                "updated_at": datetime.now(timezone.utc),
            }

        result = await db.execute(
            update(CB)
            .where(CB.user_id == user_id)
            .values(**values)
            .returning(CB.credits, CB.bonus_credits)
        )
        row = result.first()
        if row is None:
            return None
        return (old_credits, old_bonus, row.credits, row.bonus_credits)

    async def set_credits(
        self,
        db: AsyncSession,
        user_id: str,
        amount: Decimal,
        *,
        bonus_amount: Decimal | None = None,
    ) -> tuple[Decimal, Decimal, Decimal, Decimal] | None:
        """Set a user's credit balance to exact amounts.

        Reads the old balance with ``FOR UPDATE`` (row-level lock in PostgreSQL)
        then writes new values with ``UPDATE … RETURNING``.  Returns
        ``(old_credits, old_bonus, new_credits, new_bonus)`` so callers can
        compute accurate deltas.  Returns ``None`` if the row was not found.
        """
        CB = CreditBalanceRecord
        amount = Decimal(str(amount))

        # Lock the row to prevent concurrent modification between read and write.
        old_result = await db.execute(
            select(CB.credits, CB.bonus_credits)
            .where(CB.user_id == user_id)
            .with_for_update()
        )
        old_row = old_result.first()
        if old_row is None:
            return None
        old_credits: Decimal = old_row.credits
        old_bonus: Decimal = old_row.bonus_credits

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
        return (old_credits, old_bonus, row.credits, row.bonus_credits)
