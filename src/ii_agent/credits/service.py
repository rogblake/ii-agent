"""Credit service — atomic balance mutations and read queries.

All credit mutations follow the two-table pattern per ADR-004:
    INSERT credit_transaction → UPDATE credit_balance
inside a SAVEPOINT (``db.begin_nested()``).

Row-level locking (``SELECT ... FOR UPDATE``) serializes concurrent
mutations for the same user. Optimistic ``version`` on CreditBalance
provides an additional safety net.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import Settings
from ii_agent.sessions.models import Session
from ii_agent.credits.models import (
    CreditBalance,
    CreditTransaction,
    CreditType,
    TransactionType,
)
from ii_agent.credits.repository import (
    CreditBalanceRepository,
    CreditTransactionRepository,
)
from ii_agent.credits.schemas import (
    CreditBalanceResponse,
    CreditTransactionItem,
    CreditUsageResponse,
    CreditUsageSession,
    SessionUsageDetailResponse,
)

logger = logging.getLogger(__name__)


class CreditService:
    """Manages all credit mutations and queries.

    Constructor dependencies are injected via ``ApplicationContainer``.
    """

    def __init__(
        self,
        *,
        balance_repo: CreditBalanceRepository,
        transaction_repo: CreditTransactionRepository,
        config: Settings,
    ) -> None:
        self._balance_repo = balance_repo
        self._tx_repo = transaction_repo
        self._config = config

    # =====================================================================
    # Write-path: atomic mutations
    # =====================================================================

    async def deduct(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        amount: Decimal,
        transaction_type: TransactionType,
        session_id: uuid.UUID | None = None,
        run_id: uuid.UUID | None = None,
        model_id: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[CreditTransaction]:
        """Deduct credits from user's balance.

        Deduction priority (per ADR-004):
        1. Bonus balance consumed FIRST (until exhausted)
        2. Remaining deducted from regular balance

        Returns a list of transactions (one per credit pool affected).
        Atomic: INSERT transaction(s) + UPDATE balance inside SAVEPOINT.
        """
        async with db.begin_nested():
            balance = await self._balance_repo.get_for_update(db, user_id)
            if balance is None:
                raise ValueError(f"No credit balance found for user {user_id}")

            amount = abs(amount)  # Ensure positive for calculation

            # Split across bonus (first) and regular
            bonus_deduction = min(balance.bonus_credits, amount)
            regular_deduction = amount - bonus_deduction

            txns: list[CreditTransaction] = []

            if bonus_deduction > 0:
                balance.bonus_credits -= bonus_deduction
                txns.append(
                    self._build_transaction(
                        user_id=user_id,
                        transaction_type=transaction_type,
                        credit_type=CreditType.BONUS,
                        amount=-bonus_deduction,
                        balance_after=balance.bonus_credits,
                        session_id=session_id,
                        run_id=run_id,
                        model_id=model_id,
                        description=description,
                        metadata=metadata,
                    )
                )

            if regular_deduction > 0:
                balance.credits -= regular_deduction
                txns.append(
                    self._build_transaction(
                        user_id=user_id,
                        transaction_type=transaction_type,
                        credit_type=CreditType.REGULAR,
                        amount=-regular_deduction,
                        balance_after=balance.credits,
                        session_id=session_id,
                        run_id=run_id,
                        model_id=model_id,
                        description=description,
                        metadata=metadata,
                    )
                )

            balance.version += 1
            for tx in txns:
                db.add(tx)
            await db.flush()
            return txns

    async def grant(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        amount: Decimal,
        transaction_type: TransactionType,
        credit_type: CreditType = CreditType.REGULAR,
        billing_transaction_id: uuid.UUID | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CreditTransaction:
        """Add credits to user's balance.

        Atomic: INSERT transaction + UPDATE balance inside SAVEPOINT.
        """
        amount = abs(amount)

        async with db.begin_nested():
            balance = await self._balance_repo.get_for_update(db, user_id)
            if balance is None:
                raise ValueError(f"No credit balance found for user {user_id}")

            if credit_type == CreditType.BONUS:
                balance.bonus_credits += amount
                balance_after = balance.bonus_credits
            else:
                balance.credits += amount
                balance_after = balance.credits

            tx = self._build_transaction(
                user_id=user_id,
                transaction_type=transaction_type,
                credit_type=credit_type,
                amount=amount,
                balance_after=balance_after,
                billing_transaction_id=billing_transaction_id,
                description=description,
                metadata=metadata,
            )
            db.add(tx)
            await db.flush()
            return tx

    async def set_subscription_credits(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        plan_credits: Decimal,
        billing_transaction_id: uuid.UUID,
        plan_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> CreditTransaction:
        """Reset regular balance to plan amount on subscription renewal.

        Not additive — SETS the balance. Transaction records the delta.
        Uses SUBSCRIPTION_GRANT for positive deltas and ADJUSTMENT for
        negative deltas (downgrade).
        """
        async with db.begin_nested():
            balance = await self._balance_repo.get_for_update(db, user_id)
            if balance is None:
                raise ValueError(f"No credit balance found for user {user_id}")

            delta = plan_credits - balance.credits
            balance.credits = plan_credits
            balance.version += 1

            # Positive delta = grant, negative = adjustment (downgrade)
            tx_type = (
                TransactionType.SUBSCRIPTION_GRANT if delta >= 0 else TransactionType.ADJUSTMENT
            )

            tx = self._build_transaction(
                user_id=user_id,
                transaction_type=tx_type,
                credit_type=CreditType.REGULAR,
                amount=delta,
                balance_after=balance.credits,
                billing_transaction_id=billing_transaction_id,
                description=f"Subscription renewal: {plan_id}",
                metadata={"plan_id": plan_id, **(metadata or {})},
            )
            db.add(tx)
            await db.flush()
            return tx

    async def ensure_balance_exists(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        credits: Decimal = Decimal("0"),
        bonus_credits: Decimal = Decimal("0"),
    ) -> CreditBalance:
        """Create a CreditBalance row if none exists (idempotent)."""
        existing = await self._balance_repo.get_by_user_id(db, user_id)
        if existing is not None:
            return existing

        balance = CreditBalance(
            user_id=user_id,
            credits=credits,
            bonus_credits=bonus_credits,
            billing_status="ok",
        )
        return await self._balance_repo.save(db, balance)

    # =====================================================================
    # Read-path: queries
    # =====================================================================

    async def get_balance(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> CreditBalanceResponse | None:
        bal = await self._balance_repo.get_by_user_id(db, user_id)
        if bal is None:
            return None
        return CreditBalanceResponse(
            user_id=bal.user_id,
            credits=float(bal.credits),
            bonus_credits=float(bal.bonus_credits),
            updated_at=bal.updated_at,
        )

    async def has_sufficient_credits(
        self, db: AsyncSession, user_id: uuid.UUID, required: Decimal = Decimal("1")
    ) -> bool:
        bal = await self._balance_repo.get_by_user_id(db, user_id)
        if bal is None:
            return False
        return bal.total >= required

    async def get_usage_by_session(
        self, db: AsyncSession, user_id: uuid.UUID, page: int, per_page: int
    ) -> CreditUsageResponse:
        sessions, total = await self._tx_repo.get_session_summaries(db, user_id, page, per_page)
        return CreditUsageResponse(
            sessions=[CreditUsageSession(**s) for s in sessions],
            total=total,
        )

    async def get_session_usage_detail(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        page: int,
        per_page: int,
    ) -> SessionUsageDetailResponse:
        items, total_items = await self._tx_repo.get_by_session(
            db, user_id, session_id, page, per_page
        )
        total_credits = await self._tx_repo.get_session_total_credits(db, user_id, session_id)

        # Fetch session title
        result = await db.execute(select(Session.name).where(Session.id == session_id))
        session_title = result.scalar_one_or_none() or session_id

        return SessionUsageDetailResponse(
            session_id=session_id,
            session_title=session_title,
            items=[self._tx_to_item(tx) for tx in items],
            total_credits=float(total_credits),
            total_items=total_items,
        )

    async def get_transaction_history(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        page: int,
        per_page: int,
        transaction_type: str | None = None,
    ) -> tuple[list[CreditTransactionItem], int]:
        txns, total = await self._tx_repo.get_by_user(
            db, user_id, page, per_page, transaction_type=transaction_type
        )
        return [self._tx_to_item(tx) for tx in txns], total

    # =====================================================================
    # Private helpers
    # =====================================================================

    @staticmethod
    def _build_transaction(
        *,
        user_id: uuid.UUID,
        transaction_type: TransactionType,
        credit_type: CreditType,
        amount: Decimal,
        balance_after: Decimal,
        session_id: uuid.UUID | None = None,
        run_id: uuid.UUID | None = None,
        model_id: str | None = None,
        billing_transaction_id: uuid.UUID | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CreditTransaction:
        return CreditTransaction(
            user_id=user_id,
            transaction_type=transaction_type,
            credit_type=credit_type,
            amount=amount,
            balance_after=balance_after,
            session_id=session_id,
            run_id=run_id,
            model_id=model_id,
            billing_transaction_id=billing_transaction_id,
            description=description,
            data=metadata or {},
        )

    @staticmethod
    def _tx_to_item(tx: CreditTransaction) -> CreditTransactionItem:
        return CreditTransactionItem(
            id=tx.id,
            transaction_type=tx.transaction_type,
            credit_type=tx.credit_type,
            amount=float(tx.amount),
            balance_after=float(tx.balance_after),
            model_id=tx.model_id,
            run_id=tx.run_id,
            description=tx.description,
            metadata=tx.data,
            created_at=tx.created_at,
        )
