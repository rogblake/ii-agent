"""Credit management service."""

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

logger = logging.getLogger(__name__)


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
    ) -> None:
        self._balance_repo = balance_repo
        self._ledger_repo = ledger_repo or CreditLedgerRepository()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_balance(
        self, db: AsyncSession, user_id: str
    ) -> Optional[CreditBalance]:
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

    async def has_sufficient(
        self, db: AsyncSession, user_id: str, amount: float
    ) -> bool:
        """Check if user has sufficient credits (regular + bonus) for *amount*."""
        return await self._balance_repo.check_sufficient(
            db, user_id, Decimal(str(amount))
        )

    async def require_billing_ok(self, db: AsyncSession, user_id: str) -> None:
        """Raise if the account is blocked by billing reconciliation.

        Lightweight pre-flight check for billing paths that do not yet
        use the full reservation pipeline.
        """
        from ii_agent.billing.credits.balance_models import BillingStatus
        from ii_agent.billing.exceptions import BillingReconciliationRequiredError

        status = await self._balance_repo.get_billing_status(db, user_id)
        if status is not None and status != BillingStatus.OK:
            raise BillingReconciliationRequiredError(
                "Account requires billing reconciliation"
            )

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
                # 1. Lock the balance row and read current values.
                balance = await self._balance_repo.lock_balance(db, user_id)
                if balance is None:
                    logger.error("User %s not found for credit deduction", user_id)
                    return False

                old_credits = Decimal(str(balance[0]))
                old_bonus = Decimal(str(balance[1]))
                if (old_credits + old_bonus) < dec_amount:
                    logger.warning(
                        "Insufficient credits for user %s: requested %.4f, available %.4f",
                        user_id, amount, float(old_credits + old_bonus),
                    )
                    return False

                # 2. Compute the bonus-first deduction split.
                bonus_deducted = min(old_bonus, dec_amount)
                credits_deducted = dec_amount - bonus_deducted
                delta_bonus = -bonus_deducted
                delta_credits = -credits_deducted

                # Pre-compute balance-after for the ledger snapshot.
                expected_credits_after = old_credits - credits_deducted
                expected_bonus_after = old_bonus - bonus_deducted

                # 3. Try the ledger append first — it is idempotent.
                #    If the idempotency_key already exists the INSERT is
                #    a no-op and we return None (already charged).
                ledger_entry = await self._ledger_repo.append(
                    db,
                    user_id=user_id,
                    entry_type=LedgerEntryType.DEDUCTION,
                    source_domain=source_domain,
                    source_id=source_id,
                    delta_credits=delta_credits,
                    delta_bonus_credits=delta_bonus,
                    balance_after_credits=expected_credits_after,
                    balance_after_bonus_credits=expected_bonus_after,
                    entry_metadata=entry_metadata,
                    idempotency_key=idempotency_key,
                )
                if ledger_entry is None:
                    # Duplicate — balance was already deducted in a prior call.
                    logger.info(
                        "Duplicate deduction skipped for user %s (key=%s)",
                        user_id, idempotency_key,
                    )
                    return None

                # 4. Ledger entry created — now apply the balance deduction.
                #    Row is already locked by lock_balance above, so use
                #    _apply_deduction to avoid a redundant FOR UPDATE.
                new_values = await self._balance_repo._apply_deduction(
                    db, user_id, dec_amount
                )
                if new_values is None:
                    # Should not happen (we verified above), but be safe.
                    logger.error(
                        "Balance deduction failed unexpectedly for user %s", user_id
                    )
                    return False

                credits_after, bonus_after = new_values

            logger.info(
                "Deducted %.4f credits from user %s. Balance: %.4f + %.4f bonus",
                amount, user_id, float(credits_after), float(bonus_after),
            )
            return CreditDeductionResult(
                ledger_entry_id=ledger_entry.id,
                charged_credits=delta_credits,
                charged_bonus_credits=delta_bonus,
            )

        except SQLAlchemyError:
            logger.error("DB error deducting credits for %s", user_id, exc_info=True)
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
                # 1. Lock the balance row and read current values.
                balance = await self._balance_repo.lock_balance(db, user_id)
                if balance is None:
                    logger.error("User %s not found for credit addition", user_id)
                    return False

                old_credits = Decimal(str(balance[0]))
                old_bonus = Decimal(str(balance[1]))

                # 2. Pre-compute expected values for the ledger snapshot.
                if is_bonus:
                    expected_credits_after = old_credits
                    expected_bonus_after = old_bonus + dec_amount
                else:
                    expected_credits_after = old_credits + dec_amount
                    expected_bonus_after = old_bonus

                delta_credits = expected_credits_after - old_credits
                delta_bonus = expected_bonus_after - old_bonus

                # 3. Ledger first — idempotent via ON CONFLICT DO NOTHING.
                ledger_entry = await self._ledger_repo.append(
                    db,
                    user_id=user_id,
                    entry_type=entry_type,
                    source_domain=source_domain,
                    source_id=source_id,
                    delta_credits=delta_credits,
                    delta_bonus_credits=delta_bonus,
                    balance_after_credits=expected_credits_after,
                    balance_after_bonus_credits=expected_bonus_after,
                    entry_metadata=entry_metadata,
                    idempotency_key=idempotency_key,
                )
                if ledger_entry is None:
                    # Duplicate — credits were already added in a prior call.
                    logger.info(
                        "Duplicate add skipped for user %s (key=%s)",
                        user_id, idempotency_key,
                    )
                    return None

                # 4. Ledger entry created — now apply the balance addition.
                #    Row is already locked by lock_balance above.
                updated = await self._balance_repo.add_credits(
                    db, user_id, dec_amount, is_bonus=is_bonus
                )
                if not updated:
                    logger.error(
                        "Balance addition failed unexpectedly for user %s", user_id
                    )
                    return False

                _, _, credits_after, bonus_after = updated

            logger.info(
                "Added %.4f %s credits to user %s. Balance: %.4f + %.4f bonus",
                amount, "bonus" if is_bonus else "regular",
                user_id, float(credits_after), float(bonus_after),
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

                # 2. Lock the balance row and read current values.
                balance = await self._balance_repo.lock_balance(db, user_id)
                if balance is None:
                    logger.error("User %s not found for set_balance", user_id)
                    return False

                old_credits = Decimal(str(balance[0]))
                old_bonus = Decimal(str(balance[1]))

                # 3. Pre-compute deltas for the ledger snapshot.
                expected_bonus_after = dec_bonus if dec_bonus is not None else old_bonus
                delta_credits = dec_amount - old_credits
                delta_bonus = expected_bonus_after - old_bonus

                # 4. Ledger first — idempotent via ON CONFLICT DO NOTHING.
                ledger_entry = await self._ledger_repo.append(
                    db,
                    user_id=user_id,
                    entry_type=entry_type,
                    source_domain=source_domain,
                    source_id=source_id,
                    delta_credits=delta_credits,
                    delta_bonus_credits=delta_bonus,
                    balance_after_credits=dec_amount,
                    balance_after_bonus_credits=expected_bonus_after,
                    entry_metadata=entry_metadata,
                    idempotency_key=idempotency_key,
                )
                if idempotency_key is not None and ledger_entry is None:
                    # Duplicate — balance was already set in a prior call.
                    logger.info(
                        "Duplicate set_balance skipped for user %s (key=%s)",
                        user_id, idempotency_key,
                    )
                    return None

                # 5. Ledger entry created — now apply the balance change.
                #    Row is already locked by lock_balance above.
                updated = await self._balance_repo.set_credits(
                    db, user_id, dec_amount, bonus_amount=dec_bonus
                )
                if not updated:
                    logger.error(
                        "set_credits failed unexpectedly for user %s", user_id
                    )
                    return False

                _, _, credits_after, bonus_after = updated

            logger.info(
                "Set credits for user %s: %.4f + %.4f bonus",
                user_id, float(credits_after), float(bonus_after),
            )
            return True

        except SQLAlchemyError:
            logger.error("DB error setting credits for %s", user_id, exc_info=True)
            raise

    # ------------------------------------------------------------------
    # Billing status
    # ------------------------------------------------------------------

    async def clear_billing_status(
        self, db: AsyncSession, user_id: str
    ) -> bool:
        """Reset billing status to ``ok`` if currently ``reconciliation_required``.

        Called after a successful payment event (invoice.payment_succeeded)
        so that users are not permanently blocked by a prior shortfall.
        Returns ``True`` if the status was cleared, ``False`` if it was
        already ok or the user was not found.
        """
        from ii_agent.billing.credits.balance_models import BillingStatus

        try:
            async with db.begin_nested():
                balance = await self._balance_repo.lock_balance_state(db, user_id)
                if balance is None:
                    return False
                _credits, _bonus, current_status = balance
                if current_status == BillingStatus.OK:
                    return False

                await self._balance_repo.apply_delta_locked(
                    db,
                    user_id,
                    delta_credits=Decimal("0"),
                    delta_bonus_credits=Decimal("0"),
                    billing_status=BillingStatus.OK,
                    billing_status_reason=None,
                )
            logger.info("Cleared billing status for user %s", user_id)
            return True
        except SQLAlchemyError:
            logger.error(
                "DB error clearing billing status for %s", user_id, exc_info=True
            )
            raise

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
        return await self._ledger_repo.get_history(
            db, user_id, page=page, per_page=per_page
        )

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
