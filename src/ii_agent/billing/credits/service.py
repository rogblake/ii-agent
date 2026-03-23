"""Credit management service."""

from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.credits.balance_repository import CreditBalanceRepository
from ii_agent.billing.credits.ledger_models import LedgerEntryType
from ii_agent.billing.credits.ledger_repository import CreditLedgerRepository
from ii_agent.billing.credits.schemas import CreditBalance
from ii_agent.billing.reservations.repository import CreditReservationRepository

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _noop_async_context():
    yield


@dataclass(frozen=True)
class CreditDeductionResult:
    """Successful credit deduction details for downstream dual-writes."""

    ledger_entry_id: int
    charged_credits: Decimal
    charged_bonus_credits: Decimal

    @property
    def total_charged(self) -> Decimal:
        """Return the total absolute credits charged across buckets."""
        return abs(self.charged_credits) + abs(self.charged_bonus_credits)


@dataclass(frozen=True)
class _BalanceSnapshot:
    credits: Decimal
    bonus: Decimal

    @property
    def total(self) -> Decimal:
        return self.credits + self.bonus


@dataclass(frozen=True)
class _LedgerMutation:
    entry_type: str | LedgerEntryType
    delta_credits: Decimal
    delta_bonus_credits: Decimal
    balance_after_credits: Decimal
    balance_after_bonus_credits: Decimal


@dataclass(frozen=True)
class PlanBalanceResetResult:
    """Outcome of a hold-aware plan balance reset."""

    spendable_credits: Decimal
    held_regular_credits: Decimal
    held_bonus_credits: Decimal
    updated: bool


class CreditService:
    """Service for credit balance operations.

    All write methods use ``flush()`` only — the caller (FastAPI's
    ``DBSession`` dependency or ``get_db_session_local()``) is
    responsible for committing the transaction.

    Each mutation wraps the balance update **and** its ledger append
    inside ``db.begin_nested()`` (a SAVEPOINT) so the two operations
    are atomic: if the ledger write fails the balance change rolls
    back, and the ``FOR UPDATE`` row lock is held across both steps.
    """

    def __init__(
        self,
        *,
        balance_repo: CreditBalanceRepository,
        ledger_repo: Optional[CreditLedgerRepository] = None,
        reservation_repo: Optional[CreditReservationRepository] = None,
    ) -> None:
        self._balance_repo = balance_repo
        self._ledger_repo = ledger_repo or CreditLedgerRepository()
        self._reservation_repo = reservation_repo or CreditReservationRepository()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_balance(self, db: AsyncSession, user_id: str) -> Optional[CreditBalance]:
        """Get the current credit balance for a user."""
        result = await self._balance_repo.get_balance_with_updated_at(db, user_id)
        if result is None:
            return None
        credits, bonus_credits, updated_at = result
        return CreditBalance(
            user_id=user_id,
            credits=float(credits),
            bonus_credits=float(bonus_credits),
            updated_at=updated_at,
        )

    async def has_sufficient(self, db: AsyncSession, user_id: str, amount: float) -> bool:
        """Check if user has sufficient credits (regular + bonus) for *amount*."""
        return await self._balance_repo.check_sufficient(db, user_id, Decimal(str(amount)))

    async def require_billing_ok(self, db: AsyncSession, user_id: str) -> None:
        """Raise if the account is blocked by billing reconciliation.

        Lightweight pre-flight check for billing paths that do not yet
        use the full reservation pipeline.
        """
        from ii_agent.billing.credits.balance_models import BillingStatus
        from ii_agent.billing.exceptions import BillingReconciliationRequiredError

        status = await self._balance_repo.get_billing_status(db, user_id)
        if status is not None and status != BillingStatus.OK:
            raise BillingReconciliationRequiredError("Account requires billing reconciliation")

    async def get_balance_state_locked(
        self, db: AsyncSession, user_id: str
    ) -> tuple[Decimal, Decimal, Any] | None:
        """Return the current locked balance state for reserve-time decisions."""
        return await self._balance_repo.lock_balance_state(db, user_id)

    async def ensure_balance_exists(
        self, db: AsyncSession, user_id: str, **kwargs: Any
    ) -> tuple[Decimal, Decimal]:
        """Ensure a ``credit_balances`` row exists for *user_id*.

        Creates one with the given defaults if missing and writes an
        ``initial_balance`` ledger entry when the row is newly created
        with non-zero credits.  The insert and ledger append run inside
        a SAVEPOINT so they succeed or fail together.

        Returns ``(credits, bonus_credits)``.
        """
        existing = await self._balance_repo.get_balance(db, user_id)
        if existing is not None:
            return existing

        async with db.begin_nested():
            credits, bonus_credits, created = await self._balance_repo.get_or_create(
                db, user_id, **kwargs
            )

            if created and (credits or bonus_credits):
                await self._ledger_repo.append(
                    db,
                    user_id=user_id,
                    entry_type=LedgerEntryType.INITIAL_BALANCE,
                    delta_credits=credits,
                    delta_bonus_credits=bonus_credits,
                    balance_after_credits=credits,
                    balance_after_bonus_credits=bonus_credits,
                    idempotency_key=f"initial_balance:{user_id}",
                )

        return (credits, bonus_credits)

    # ------------------------------------------------------------------
    # Mutations (no commit — caller manages the transaction)
    # ------------------------------------------------------------------

    async def deduct(
        self,
        db: AsyncSession,
        user_id: str,
        amount: float,
        *,
        source_domain: Optional[str] = None,
        source_id: Optional[str] = None,
        entry_metadata: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
    ) -> CreditDeductionResult | bool | None:
        """Atomically deduct *amount* credits from a user.

        Bonus credits are consumed first; any remainder is taken from
        regular credits.  The ledger append (idempotent) runs before the
        balance mutation so that a duplicate idempotency key short-circuits
        without ever touching the balance.  Both operations share a single
        SAVEPOINT — if either fails the entire change rolls back.

        Returns ``CreditDeductionResult`` on success, ``None`` if the
        idempotency key was a duplicate (already charged), or ``False`` if
        insufficient balance or user not found.
        """
        try:
            dec_amount = Decimal(str(amount))

            async with db.begin_nested():
                balance = await self._lock_balance_snapshot(
                    db,
                    user_id,
                    missing_log="User %s not found for credit deduction",
                )
                if balance is None:
                    return False

                if balance.total < dec_amount:
                    logger.warning(
                        "Insufficient credits for user %s: requested %.4f, available %.4f",
                        user_id,
                        amount,
                        float(balance.total),
                    )
                    return False

                mutation = self._build_deduction_mutation(balance, dec_amount)
                mutation_result = await self._append_and_apply_locked_mutation(
                    db,
                    user_id=user_id,
                    mutation=mutation,
                    source_domain=source_domain,
                    source_id=source_id,
                    entry_metadata=entry_metadata,
                    idempotency_key=idempotency_key,
                    duplicate_log="Duplicate deduction skipped for user %s (key=%s)",
                    failure_log="Balance deduction failed unexpectedly for user %s",
                )
                if mutation_result is None:
                    return None
                if mutation_result is False:
                    return False

                ledger_entry, after = mutation_result

            logger.info(
                "Deducted %.4f credits from user %s. Balance: %.4f + %.4f bonus",
                amount,
                user_id,
                float(after.credits),
                float(after.bonus),
            )
            return CreditDeductionResult(
                ledger_entry_id=ledger_entry.id,
                charged_credits=mutation.delta_credits,
                charged_bonus_credits=mutation.delta_bonus_credits,
            )

        except SQLAlchemyError:
            logger.error("DB error deducting credits for %s", user_id, exc_info=True)
            raise

    async def deduct_locked(
        self,
        db: AsyncSession,
        user_id: str,
        amount: float,
        *,
        locked_balance: tuple[Decimal, Decimal] | _BalanceSnapshot,
        source_domain: Optional[str] = None,
        source_id: Optional[str] = None,
        entry_metadata: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
        use_savepoint: bool = False,
    ) -> CreditDeductionResult | bool | None:
        """Deduct credits while the caller already holds the balance row lock."""
        try:
            dec_amount = Decimal(str(amount))
            balance = (
                locked_balance
                if isinstance(locked_balance, _BalanceSnapshot)
                else self._balance_snapshot(locked_balance)
            )
            context = db.begin_nested() if use_savepoint else _noop_async_context()

            async with context:
                if balance.total < dec_amount:
                    logger.warning(
                        "Insufficient credits for user %s: requested %.4f, available %.4f",
                        user_id,
                        amount,
                        float(balance.total),
                    )
                    return False

                mutation = self._build_deduction_mutation(balance, dec_amount)
                mutation_result = await self._append_and_apply_locked_mutation(
                    db,
                    user_id=user_id,
                    mutation=mutation,
                    source_domain=source_domain,
                    source_id=source_id,
                    entry_metadata=entry_metadata,
                    idempotency_key=idempotency_key,
                    duplicate_log="Duplicate deduction skipped for user %s (key=%s)",
                    failure_log="Balance deduction failed unexpectedly for user %s",
                )
                if mutation_result is None:
                    return None
                if mutation_result is False:
                    return False

                ledger_entry, after = mutation_result

            logger.info(
                "Deducted %.4f credits from user %s. Balance: %.4f + %.4f bonus",
                amount,
                user_id,
                float(after.credits),
                float(after.bonus),
            )
            return CreditDeductionResult(
                ledger_entry_id=ledger_entry.id,
                charged_credits=mutation.delta_credits,
                charged_bonus_credits=mutation.delta_bonus_credits,
            )

        except SQLAlchemyError:
            logger.error("DB error deducting locked credits for %s", user_id, exc_info=True)
            raise

    async def add(
        self,
        db: AsyncSession,
        user_id: str,
        amount: float,
        *,
        is_bonus: bool = False,
        source_domain: Optional[str] = None,
        source_id: Optional[str] = None,
        entry_metadata: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
    ) -> bool | None:
        """Atomically add *amount* credits to a user.

        Uses the same lock → ledger → mutate pattern as ``deduct()``:
        the row is locked first, the ledger append (idempotent) runs
        before the balance mutation so a duplicate idempotency key
        short-circuits without ever touching the balance.  Both
        operations share a single SAVEPOINT.

        Returns ``True`` if credits were added, ``None`` if the
        idempotency key was a duplicate (already applied), or ``False``
        if the user was not found.
        """
        try:
            dec_amount = Decimal(str(amount))
            entry_type = LedgerEntryType.BONUS_GRANT if is_bonus else LedgerEntryType.GRANT

            async with db.begin_nested():
                balance = await self._lock_balance_snapshot(
                    db,
                    user_id,
                    missing_log="User %s not found for credit addition",
                )
                if balance is None:
                    return False

                mutation = self._build_add_mutation(
                    balance,
                    amount=dec_amount,
                    is_bonus=is_bonus,
                    entry_type=entry_type,
                )
                mutation_result = await self._append_and_apply_locked_mutation(
                    db,
                    user_id=user_id,
                    mutation=mutation,
                    source_domain=source_domain,
                    source_id=source_id,
                    entry_metadata=entry_metadata,
                    idempotency_key=idempotency_key,
                    duplicate_log="Duplicate add skipped for user %s (key=%s)",
                    failure_log="Balance addition failed unexpectedly for user %s",
                )
                if mutation_result is None:
                    return None
                if mutation_result is False:
                    return False

                _ledger_entry, after = mutation_result

            logger.info(
                "Added %.4f %s credits to user %s. Balance: %.4f + %.4f bonus",
                amount,
                "bonus" if is_bonus else "regular",
                user_id,
                float(after.credits),
                float(after.bonus),
            )
            return True

        except SQLAlchemyError:
            logger.error("DB error adding credits for %s", user_id, exc_info=True)
            raise

    async def set_balance(
        self,
        db: AsyncSession,
        user_id: str,
        amount: float,
        *,
        bonus_amount: Optional[float] = None,
        entry_type: str | LedgerEntryType = LedgerEntryType.PLAN_CHANGE,
        source_domain: Optional[str] = None,
        source_id: Optional[str] = None,
        entry_metadata: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
    ) -> bool | None:
        """Set a user's credit balance to exact amounts.

        Auto-creates the ``credit_balances`` row if it does not exist.
        Uses the same lock → ledger → mutate pattern as ``deduct()``:
        the ledger append (idempotent) runs before the balance mutation
        so a duplicate idempotency key short-circuits without ever
        touching the balance.

        Returns ``True`` if the balance was set, ``None`` if the
        idempotency key was a duplicate (already applied), or ``False``
        if the user was not found.
        """
        try:
            dec_amount = Decimal(str(amount))
            dec_bonus = Decimal(str(bonus_amount)) if bonus_amount is not None else None

            async with db.begin_nested():
                # 1. Ensure balance row exists inside the SAVEPOINT so
                #    a failure in ledger/set_credits rolls back the
                #    newly-created row as well.
                await self._balance_repo.get_or_create(db, user_id)

                balance = await self._lock_balance_snapshot(
                    db,
                    user_id,
                    missing_log="User %s not found for set_balance",
                )
                if balance is None:
                    return False

                after = await self._set_balance_locked(
                    db,
                    user_id=user_id,
                    amount=dec_amount,
                    bonus_amount=dec_bonus,
                    locked_balance=balance,
                    entry_type=entry_type,
                    source_domain=source_domain,
                    source_id=source_id,
                    entry_metadata=entry_metadata,
                    idempotency_key=idempotency_key,
                )
                if after is None:
                    return None
                if after is False:
                    return False

            logger.info(
                "Set credits for user %s: %.4f + %.4f bonus",
                user_id,
                float(after.credits),
                float(after.bonus),
            )
            return True

        except SQLAlchemyError:
            logger.error("DB error setting credits for %s", user_id, exc_info=True)
            raise

    async def reset_plan_balance(
        self,
        db: AsyncSession,
        user_id: str,
        plan_credits: float,
        *,
        entry_type: str | LedgerEntryType = LedgerEntryType.PLAN_CHANGE,
        source_domain: Optional[str] = None,
        source_id: Optional[str] = None,
        entry_metadata: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
    ) -> PlanBalanceResetResult:
        """Reset spendable regular credits while preserving unresolved holds.

        ``credit_reservations`` keeps unresolved holds out of the spendable
        balance. Plan refreshes and billing events must therefore reset the
        balance to ``plan_credits - outstanding_regular_holds`` rather than the
        raw plan allowance, otherwise a later release would double-credit the
        user.
        """
        plan_credits_dec = Decimal(str(plan_credits))
        async with db.begin_nested():
            # Hold the balance row lock across both the outstanding-hold read
            # and the final balance mutation so a concurrent reserve/release
            # cannot slip in between and get overwritten by the plan reset.
            await self._balance_repo.get_or_create(db, user_id)
            balance = await self._lock_balance_snapshot(
                db,
                user_id,
                missing_log="User %s not found for reset_plan_balance",
            )
            if balance is None:
                raise ValueError(f"Balance not found for user {user_id}")

            held_regular, held_bonus = await self._reservation_repo.get_outstanding_hold_totals(
                db,
                user_id=user_id,
            )
            spendable_credits = max(plan_credits_dec - held_regular, Decimal("0"))

            if balance.credits == spendable_credits:
                return PlanBalanceResetResult(
                    spendable_credits=spendable_credits,
                    held_regular_credits=held_regular,
                    held_bonus_credits=held_bonus,
                    updated=False,
                )

            metadata = dict(entry_metadata or {})
            metadata.update(
                {
                    "plan_credits": float(plan_credits_dec),
                    "held_regular_credits": float(held_regular),
                    "held_bonus_credits": float(held_bonus),
                }
            )

            result = await self._set_balance_locked(
                db,
                user_id=user_id,
                amount=spendable_credits,
                bonus_amount=None,
                locked_balance=balance,
                entry_type=entry_type,
                source_domain=source_domain,
                source_id=source_id,
                entry_metadata=metadata,
                idempotency_key=idempotency_key,
            )
            if result is False:
                raise ValueError(f"Failed to reset plan balance for user {user_id}")

        return PlanBalanceResetResult(
            spendable_credits=spendable_credits,
            held_regular_credits=held_regular,
            held_bonus_credits=held_bonus,
            updated=result is not None,
        )

    # ------------------------------------------------------------------
    # Billing status
    # ------------------------------------------------------------------

    async def clear_billing_status(self, db: AsyncSession, user_id: str) -> bool:
        """Reset billing status to ``ok`` if currently ``reconciliation_required``.

        Called after a successful payment event (invoice.payment_succeeded)
        so that users are not permanently blocked by a prior shortfall.
        Returns ``True`` if the status was cleared, ``False`` if it was
        already ok or the user was not found.
        """
        from ii_agent.billing.credits.balance_models import BillingStatus

        try:
            async with db.begin_nested():
                cleared = await self._balance_repo.set_billing_status(
                    db,
                    user_id,
                    billing_status=BillingStatus.OK,
                    billing_status_reason=None,
                    expected_current_status=BillingStatus.RECONCILIATION_REQUIRED,
                )
                if not cleared:
                    return False
            logger.info("Cleared billing status for user %s", user_id)
            return True
        except SQLAlchemyError:
            logger.error("DB error clearing billing status for %s", user_id, exc_info=True)
            raise

    @staticmethod
    def _balance_snapshot(
        balance: tuple[Decimal, Decimal] | tuple[Decimal, Decimal, Any],
    ) -> _BalanceSnapshot:
        return _BalanceSnapshot(
            credits=Decimal(str(balance[0])),
            bonus=Decimal(str(balance[1])),
        )

    async def _lock_balance_snapshot(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        missing_log: str,
    ) -> _BalanceSnapshot | None:
        balance = await self._balance_repo.lock_balance(db, user_id)
        if balance is None:
            logger.error(missing_log, user_id)
            return None
        return self._balance_snapshot(balance)

    @staticmethod
    def _build_deduction_mutation(balance: _BalanceSnapshot, amount: Decimal) -> _LedgerMutation:
        bonus_deducted = min(balance.bonus, amount)
        credits_deducted = amount - bonus_deducted
        return _LedgerMutation(
            entry_type=LedgerEntryType.DEDUCTION,
            delta_credits=-credits_deducted,
            delta_bonus_credits=-bonus_deducted,
            balance_after_credits=balance.credits - credits_deducted,
            balance_after_bonus_credits=balance.bonus - bonus_deducted,
        )

    @staticmethod
    def _build_add_mutation(
        balance: _BalanceSnapshot,
        *,
        amount: Decimal,
        is_bonus: bool,
        entry_type: LedgerEntryType,
    ) -> _LedgerMutation:
        if is_bonus:
            return _LedgerMutation(
                entry_type=entry_type,
                delta_credits=Decimal("0"),
                delta_bonus_credits=amount,
                balance_after_credits=balance.credits,
                balance_after_bonus_credits=balance.bonus + amount,
            )
        return _LedgerMutation(
            entry_type=entry_type,
            delta_credits=amount,
            delta_bonus_credits=Decimal("0"),
            balance_after_credits=balance.credits + amount,
            balance_after_bonus_credits=balance.bonus,
        )

    @staticmethod
    def _build_set_balance_mutation(
        balance: _BalanceSnapshot,
        *,
        amount: Decimal,
        bonus_amount: Decimal | None,
        entry_type: str | LedgerEntryType,
    ) -> _LedgerMutation:
        expected_bonus_after = bonus_amount if bonus_amount is not None else balance.bonus
        return _LedgerMutation(
            entry_type=entry_type,
            delta_credits=amount - balance.credits,
            delta_bonus_credits=expected_bonus_after - balance.bonus,
            balance_after_credits=amount,
            balance_after_bonus_credits=expected_bonus_after,
        )

    async def _set_balance_locked(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        amount: Decimal,
        bonus_amount: Decimal | None,
        locked_balance: _BalanceSnapshot,
        entry_type: str | LedgerEntryType,
        source_domain: Optional[str],
        source_id: Optional[str],
        entry_metadata: Optional[dict],
        idempotency_key: Optional[str],
    ) -> _BalanceSnapshot | bool | None:
        """Set exact balances while the caller already owns the balance lock."""
        mutation = self._build_set_balance_mutation(
            locked_balance,
            amount=amount,
            bonus_amount=bonus_amount,
            entry_type=entry_type,
        )
        mutation_result = await self._append_and_apply_locked_mutation(
            db,
            user_id=user_id,
            mutation=mutation,
            source_domain=source_domain,
            source_id=source_id,
            entry_metadata=entry_metadata,
            idempotency_key=idempotency_key,
            duplicate_log="Duplicate set_balance skipped for user %s (key=%s)",
            failure_log="set_credits failed unexpectedly for user %s",
            set_balance_to=(amount, bonus_amount),
        )
        if mutation_result is None:
            return None
        if mutation_result is False:
            return False

        _ledger_entry, after = mutation_result
        return after

    async def _append_and_apply_locked_mutation(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        mutation: _LedgerMutation,
        source_domain: Optional[str],
        source_id: Optional[str],
        entry_metadata: Optional[dict],
        idempotency_key: Optional[str],
        duplicate_log: str,
        failure_log: str,
        set_balance_to: tuple[Decimal, Decimal | None] | None = None,
    ) -> tuple[Any, _BalanceSnapshot] | bool | None:
        ledger_entry = await self._ledger_repo.append(
            db,
            user_id=user_id,
            entry_type=mutation.entry_type,
            source_domain=source_domain,
            source_id=source_id,
            delta_credits=mutation.delta_credits,
            delta_bonus_credits=mutation.delta_bonus_credits,
            balance_after_credits=mutation.balance_after_credits,
            balance_after_bonus_credits=mutation.balance_after_bonus_credits,
            entry_metadata=entry_metadata,
            idempotency_key=idempotency_key,
        )
        if ledger_entry is None:
            logger.info(duplicate_log, user_id, idempotency_key)
            return None

        if set_balance_to is None:
            new_values = await self._balance_repo.apply_delta_locked(
                db,
                user_id,
                delta_credits=mutation.delta_credits,
                delta_bonus_credits=mutation.delta_bonus_credits,
            )
        else:
            amount, bonus_amount = set_balance_to
            new_values = await self._balance_repo._set_credits_locked(
                db,
                user_id,
                amount,
                bonus_amount=bonus_amount,
            )
        if new_values is None:
            logger.error(failure_log, user_id)
            return False
        return ledger_entry, self._balance_snapshot(new_values)

    # ------------------------------------------------------------------
    # Ledger history
    # ------------------------------------------------------------------

    async def get_ledger_history(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list, int]:
        """Get paginated credit ledger entries for a user."""
        return await self._ledger_repo.get_history(db, user_id, page=page, per_page=per_page)

    async def get_session_ledger_history(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
        *,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list, int]:
        """Get paginated credit ledger entries for a specific session."""
        return await self._ledger_repo.get_history_by_session(
            db, user_id, session_id, page=page, per_page=per_page
        )

    async def get_subject_ledger_history(
        self,
        db: AsyncSession,
        user_id: str,
        subject_kind: str,
        subject_id: str,
        *,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list, int]:
        """Get paginated credit ledger entries for a specific billing subject."""
        return await self._ledger_repo.get_history_by_subject(
            db,
            user_id,
            subject_kind,
            subject_id,
            page=page,
            per_page=per_page,
        )
