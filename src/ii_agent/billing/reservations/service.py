"""Reservation service for prepaid LLM and tool billing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.policy import (
    CONTROLLED_SHORTFALL_MAX_CREDITS,
    controlled_shortfall_admission_allowed,
    controlled_shortfall_required_credits,
)
from ii_agent.billing.credits.balance_models import BillingStatus
from ii_agent.billing.credits.balance_repository import CreditBalanceRepository
from ii_agent.billing.credits.ledger_repository import CreditLedgerRepository
from ii_agent.billing.credits.service import CreditDeductionResult, CreditService
from ii_agent.billing.credits.utils import usd_to_credits
from ii_agent.billing.reservations.repository import CreditReservationRepository
from ii_agent.billing.credits.ledger_models import LedgerEntryType
from ii_agent.billing.reservations.types import (
    BillingQuote,
    BillingSettlementResult,
    ReservationHold,
    SETTLEMENT_ERROR_SHORTFALL_UNRECONCILED,
    ReservationStatus,
)
from ii_agent.billing.exceptions import (
    BillingReconciliationRequiredError,
    InsufficientCreditsError,
)
from ii_agent.billing.usage.service import UsageService

logger = logging.getLogger(__name__)

# Terminal statuses — no further state transitions allowed.
_TERMINAL_STATUSES = frozenset(
    {
        ReservationStatus.SETTLED,
        ReservationStatus.RELEASED,
        ReservationStatus.EXPIRED,
    }
)

# last_error values for settle outcomes.
_LAST_ERROR_SHORTFALL = SETTLEMENT_ERROR_SHORTFALL_UNRECONCILED
_LAST_ERROR_SETTLEMENT_REFUND = "settlement_refund"
_LAST_ERROR_CAPTURED_STALE_RECOVERY_FAILED = "captured_stale_recovery_failed"
_MANUAL_SETTLEMENT_CAPTURE_KEY = "manual_settlement_capture"


@dataclass(frozen=True)
class _CreditBuckets:
    regular: Decimal
    bonus: Decimal

    @property
    def total(self) -> Decimal:
        return self.regular + self.bonus


@dataclass(frozen=True)
class _SettlementBreakdown:
    reserved: _CreditBuckets
    actual_regular: Decimal
    actual_bonus: Decimal
    refund_regular: Decimal
    refund_bonus: Decimal
    shortfall: Decimal

    @property
    def actual_requested(self) -> Decimal:
        return self.actual_regular + self.actual_bonus + self.shortfall


@dataclass(frozen=True)
class _ShortfallOutcome:
    charged_regular: Decimal = Decimal("0")
    charged_bonus: Decimal = Decimal("0")
    ledger_entry_id: int | None = None
    settlement_status: ReservationStatus = ReservationStatus.SETTLED
    shortfall_detected: bool = False


class CreditReservationService:
    """Reserve credits up front, then settle or release them after work finishes."""

    def __init__(
        self,
        *,
        balance_repo: CreditBalanceRepository,
        ledger_repo: CreditLedgerRepository,
        reservation_repo: CreditReservationRepository,
        credit_service: CreditService,
        usage_service: UsageService,
    ) -> None:
        self._balance_repo = balance_repo
        self._ledger_repo = ledger_repo
        self._reservation_repo = reservation_repo
        self._credit_service = credit_service
        self._usage_service = usage_service

    async def reserve(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        billing_context: str = "unknown",
        subject_kind: str = "session",
        subject_id: str | None = None,
        source_domain: str,
        source_id: str,
        billing_kind: str,
        quote: BillingQuote,
        run_id: str | None = None,
        model_id: str | None = None,
        tool_name: str | None = None,
        idempotency_key: str,
        metadata: dict[str, Any] | None = None,
        expires_in: timedelta | None = None,
        output_token_cap: int | None = None,
    ) -> ReservationHold | None:
        """Reserve credits synchronously before starting paid work."""
        if not idempotency_key:
            raise ValueError("idempotency_key is required for credit reservations")
        reserve_target_total = usd_to_credits(quote.reserve_usd)
        admission_required_total = usd_to_credits(quote.max_usd)
        if reserve_target_total <= 0:
            return None

        expires_at = (
            datetime.now(timezone.utc) + expires_in
            if expires_in is not None
            else datetime.now(timezone.utc) + timedelta(minutes=30)
        )

        async with db.begin_nested():
            # Lock balance first to serialise concurrent reserves for the
            # same user — this also prevents the TOCTOU race on the
            # idempotency check because any competing reserve for the same
            # user is blocked until this savepoint completes.
            balance = await self._balance_repo.lock_balance_state(db, user_id)
            if balance is None:
                raise InsufficientCreditsError(
                    "Credit balance not found",
                    phase="reserve",
                )

            old_credits, old_bonus, billing_status = balance
            if billing_status != BillingStatus.OK:
                raise BillingReconciliationRequiredError("Billing reconciliation required")

            # Now check idempotency — under the balance lock, so no race.
            existing = await self._reservation_repo.get_by_idempotency_key(db, idempotency_key)
            if existing is not None:
                return self._build_hold(
                    existing,
                    output_token_cap=output_token_cap,
                    was_created=False,
                )

            available_total = old_credits + old_bonus
            if available_total <= 0:
                raise InsufficientCreditsError(
                    "Insufficient credits",
                    phase="reserve",
                    available_credits=float(available_total),
                    required_credits=1.0,
                )
            if not controlled_shortfall_admission_allowed(
                available_credits=available_total,
                required_credits=admission_required_total,
            ):
                raise InsufficientCreditsError(
                    "Insufficient credits",
                    phase="reserve",
                    available_credits=float(available_total),
                    required_credits=float(
                        controlled_shortfall_required_credits(admission_required_total)
                    ),
                )

            reserved_total = min(available_total, reserve_target_total)

            reserved_bonus = min(old_bonus, reserved_total)
            reserved_credits = reserved_total - reserved_bonus
            expected_credits_after = old_credits - reserved_credits
            expected_bonus_after = old_bonus - reserved_bonus
            entry_metadata = {
                **(metadata or {}),
                "billing_context": billing_context,
                "billing_kind": billing_kind,
                "quote_strategy": quote.strategy,
                "quoted_usd": float(quote.reserve_usd),
                "max_usd": float(quote.max_usd),
                "reservation_source_id": source_id,
                "output_token_cap": output_token_cap,
                "requested_reserve_credits": float(reserve_target_total),
                "requested_max_credits": float(admission_required_total),
                "held_credits": float(reserved_total),
                "controlled_shortfall_cap_credits": float(CONTROLLED_SHORTFALL_MAX_CREDITS),
                "partial_reserve": reserved_total < reserve_target_total,
            }

            ledger_entry = await self._ledger_repo.append(
                db,
                user_id=user_id,
                entry_type=LedgerEntryType.RESERVATION_HOLD,
                source_domain=source_domain,
                source_id=source_id,
                delta_credits=-reserved_credits,
                delta_bonus_credits=-reserved_bonus,
                balance_after_credits=expected_credits_after,
                balance_after_bonus_credits=expected_bonus_after,
                entry_metadata=entry_metadata,
                idempotency_key=idempotency_key,
            )
            if ledger_entry is None:
                # Ledger idempotency conflict — another transaction already
                # wrote the hold.  Re-check under lock for the reservation.
                existing = await self._reservation_repo.get_by_idempotency_key(db, idempotency_key)
                if existing is not None:
                    return self._build_hold(
                        existing,
                        output_token_cap=output_token_cap,
                        was_created=False,
                    )
                # The ledger entry exists but the reservation row does not.
                # This can only happen if the winner crashed between ledger
                # append and reservation create.  Log for operator attention
                # but do not silently swallow — raise so the caller sees a
                # billing error rather than proceeding without a hold.
                logger.error(
                    "Ledger idempotency conflict but reservation not found "
                    "for key %s — likely partial write from a prior attempt",
                    idempotency_key,
                )
                raise InsufficientCreditsError(
                    "Billing conflict — please retry",
                    phase="reserve",
                )

            new_values = await self._balance_repo.apply_delta_locked(
                db,
                user_id,
                delta_credits=-reserved_credits,
                delta_bonus_credits=-reserved_bonus,
            )
            if new_values is None:
                raise InsufficientCreditsError(
                    "Insufficient credits",
                    phase="reserve",
                )

            reservation = await self._reservation_repo.create(
                db,
                user_id=user_id,
                billing_context=billing_context,
                subject_kind=subject_kind,
                subject_id=subject_id,
                run_id=run_id,
                source_domain=source_domain,
                source_id=source_id,
                billing_kind=billing_kind,
                quote_strategy=quote.strategy,
                status=ReservationStatus.RESERVED,
                model_id=model_id,
                tool_name=tool_name,
                idempotency_key=idempotency_key,
                reserve_ledger_entry_id=ledger_entry.id,
                reserved_credits=reserved_credits,
                reserved_bonus_credits=reserved_bonus,
                quoted_usd=quote.reserve_usd,
                max_usd=quote.max_usd,
                reservation_metadata={
                    **(metadata or {}),
                    **quote.metadata,
                    "output_token_cap": output_token_cap,
                    "requested_reserve_credits": float(reserve_target_total),
                    "requested_max_credits": float(admission_required_total),
                    "held_credits": float(reserved_total),
                    "controlled_shortfall_cap_credits": float(CONTROLLED_SHORTFALL_MAX_CREDITS),
                    "partial_reserve": reserved_total < reserve_target_total,
                },
                expires_at=expires_at,
            )

        return self._build_hold(
            reservation,
            output_token_cap=output_token_cap,
            was_created=True,
        )

    async def get_hold_by_idempotency_key(
        self,
        db: AsyncSession,
        *,
        idempotency_key: str,
    ) -> ReservationHold | None:
        """Return an existing reservation hold for an idempotency key."""
        reservation = await self._reservation_repo.get_by_idempotency_key(db, idempotency_key)
        if reservation is None:
            return None
        return self._build_hold(reservation, output_token_cap=None, was_created=False)

    async def release(
        self,
        db: AsyncSession,
        *,
        reservation_id: str,
        reason: str,
    ) -> BillingSettlementResult:
        """Release a reservation when work did not produce a billable result."""
        async with db.begin_nested():
            reservation = await self._lock_reservation_or_raise(db, reservation_id)
            terminal_result = self._terminal_result_if_blocked(
                reservation,
                treat_settlement_failed_as_terminal=True,
            )
            if terminal_result is not None:
                return terminal_result

            target_status = self._release_status_for_reason(reason)
            return await self._release_reservation(
                db,
                reservation=reservation,
                reason=reason,
                target_status=target_status,
            )

    async def settle(
        self,
        db: AsyncSession,
        *,
        reservation_id: str,
        actual_credits: Decimal,
        actual_usd: Decimal,
        usage_payload: dict[str, Any],
    ) -> BillingSettlementResult:
        """Finalize a hold using the actual billable amount."""
        actual_credits = Decimal(str(actual_credits))
        actual_usd = Decimal(str(actual_usd))

        async with db.begin_nested():
            reservation = await self._lock_reservation_or_raise(db, reservation_id)
            terminal_result = self._terminal_result_if_blocked(reservation)
            if terminal_result is not None:
                return terminal_result

            # Zero-cost settle → inline release (avoid nested savepoint).
            if actual_credits <= 0:
                return await self._release_reservation(
                    db,
                    reservation=reservation,
                    reason="unused",
                    target_status=ReservationStatus.RELEASED,
                    actual_usd=actual_usd,
                    usage_payload=usage_payload,
                )

            breakdown = self._compute_settlement_breakdown(
                reservation=reservation,
                actual_credits=actual_credits,
            )
            locked_balance = await self._lock_balance_if_needed(
                db,
                user_id=reservation.user_id,
                needs_lock=(
                    breakdown.refund_regular > 0
                    or breakdown.refund_bonus > 0
                    or breakdown.shortfall > 0
                ),
            )
            release_ledger_id = await self._refund_unused_credits(
                db,
                reservation=reservation,
                breakdown=breakdown,
                locked_balance=locked_balance,
            )
            shortfall = await self._charge_settlement_shortfall(
                db,
                reservation=reservation,
                shortfall=breakdown.shortfall,
                locked_balance=locked_balance,
            )
            total_regular = breakdown.actual_regular + shortfall.charged_regular
            total_bonus = breakdown.actual_bonus + shortfall.charged_bonus
            usage_record_id = await self._record_settled_usage(
                db,
                reservation=reservation,
                breakdown=breakdown,
                settlement_status=shortfall.settlement_status,
                settled_total=total_regular + total_bonus,
                ledger_entry_id=(shortfall.ledger_entry_id or reservation.reserve_ledger_entry_id),
                usage_payload=usage_payload,
                actual_usd=actual_usd,
            )
            self._apply_settlement_state(
                reservation,
                settlement_status=shortfall.settlement_status,
                charged_regular=total_regular,
                charged_bonus=total_bonus,
                refund_regular=breakdown.refund_regular,
                refund_bonus=breakdown.refund_bonus,
                actual_usd=actual_usd,
                usage_record_id=usage_record_id,
                release_ledger_id=release_ledger_id,
                shortfall_ledger_id=shortfall.ledger_entry_id,
                shortfall_detected=shortfall.shortfall_detected,
            )
            await db.flush()
            if shortfall.settlement_status == ReservationStatus.SETTLED:
                await self._maybe_clear_reconciliation_required(
                    db,
                    user_id=reservation.user_id,
                )

        return BillingSettlementResult(
            reservation_id=reservation.id,
            status=shortfall.settlement_status,
            charged_credits=total_regular,
            charged_bonus_credits=total_bonus,
            released_credits=breakdown.refund_regular,
            released_bonus_credits=breakdown.refund_bonus,
            usage_record_id=usage_record_id,
            shortfall_detected=shortfall.shortfall_detected,
        )

    async def capture_settlement_input(
        self,
        db: AsyncSession,
        *,
        reservation_id: str,
        actual_credits: Decimal,
        actual_usd: Decimal,
        usage_payload: dict[str, Any],
    ) -> None:
        """Persist exact settle inputs so failed settlements can be replayed manually."""
        async with db.begin_nested():
            reservation = await self._reservation_repo.lock_by_id(db, reservation_id)
            if reservation is None:
                raise ValueError(f"Reservation {reservation_id} not found")

            metadata = self._metadata_dict(reservation.reservation_metadata)
            metadata[_MANUAL_SETTLEMENT_CAPTURE_KEY] = {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "actual_credits": str(Decimal(str(actual_credits))),
                "actual_usd": str(Decimal(str(actual_usd))),
                "usage_payload": dict(usage_payload),
            }
            reservation.reservation_metadata = metadata
            await db.flush()

    async def retry_settlement_from_capture(
        self,
        db: AsyncSession,
        *,
        reservation_id: str,
    ) -> BillingSettlementResult:
        """Replay settlement manually from the reservation's captured usage snapshot."""
        reservation = await self._reservation_repo.get_by_id(db, reservation_id)
        if reservation is None:
            raise ValueError(f"Reservation {reservation_id} not found")

        metadata = self._metadata_dict(reservation.reservation_metadata)
        capture = metadata.get(_MANUAL_SETTLEMENT_CAPTURE_KEY)
        if not isinstance(capture, dict):
            raise ValueError(f"Reservation {reservation_id} has no captured settlement input")

        usage_payload = capture.get("usage_payload")
        if not isinstance(usage_payload, dict):
            raise ValueError(f"Reservation {reservation_id} has invalid captured usage payload")

        return await self.settle(
            db,
            reservation_id=reservation_id,
            actual_credits=Decimal(str(capture.get("actual_credits", "0"))),
            actual_usd=Decimal(str(capture.get("actual_usd", "0"))),
            usage_payload=usage_payload,
        )

    async def expire_stale(
        self,
        db: AsyncSession,
        *,
        older_than: datetime,
        limit: int = 100,
    ) -> int:
        """Recover stale reservations by releasing or replaying captured work."""
        stale = await self._reservation_repo.list_stale_reserved(
            db, older_than=older_than, limit=limit
        )
        recovered = 0
        for reservation in stale:
            if self._has_captured_settlement_input(reservation):
                try:
                    await self.retry_settlement_from_capture(
                        db,
                        reservation_id=reservation.id,
                    )
                except Exception:
                    logger.error(
                        "Failed to recover stale captured reservation %s; "
                        "marking settlement_failed",
                        reservation.id,
                        exc_info=True,
                    )
                    await self.mark_settlement_failed(
                        db,
                        reservation_id=reservation.id,
                        error=_LAST_ERROR_CAPTURED_STALE_RECOVERY_FAILED,
                    )
                recovered += 1
                continue

            await self.release(
                db,
                reservation_id=reservation.id,
                reason=ReservationStatus.EXPIRED.value,
            )
            recovered += 1
        return recovered

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_key(base_key: str | None, suffix: str) -> str | None:
        """Build a derived idempotency key, or None if the base is absent."""
        if base_key is None:
            return None
        return f"{base_key}:{suffix}"

    @staticmethod
    def _terminal_result(reservation) -> BillingSettlementResult:
        """Build a result for an already-terminal reservation."""
        status = ReservationStatus(reservation.status)
        return BillingSettlementResult(
            reservation_id=reservation.id,
            status=status,
            charged_credits=Decimal(str(reservation.actual_credits or 0)),
            charged_bonus_credits=Decimal(str(reservation.actual_bonus_credits or 0)),
            released_credits=Decimal(str(reservation.released_credits or 0)),
            released_bonus_credits=Decimal(str(reservation.released_bonus_credits or 0)),
            usage_record_id=reservation.usage_record_id,
        )

    def _build_hold(
        self,
        reservation,
        *,
        output_token_cap: int | None,
        was_created: bool,
    ) -> ReservationHold:
        metadata = reservation.reservation_metadata or {}
        return ReservationHold(
            reservation_id=reservation.id,
            idempotency_key=reservation.idempotency_key or "",
            reserved_credits=Decimal(str(reservation.reserved_credits)),
            reserved_bonus_credits=Decimal(str(reservation.reserved_bonus_credits)),
            quoted_usd=Decimal(str(reservation.quoted_usd)),
            max_usd=Decimal(str(reservation.max_usd)),
            output_token_cap=output_token_cap or metadata.get("output_token_cap"),
            status=ReservationStatus(reservation.status),
            was_created=was_created,
        )

    @staticmethod
    def _metadata_dict(value: dict | None) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        return {}

    @classmethod
    def _has_captured_settlement_input(cls, reservation) -> bool:
        metadata = cls._metadata_dict(getattr(reservation, "reservation_metadata", None))
        return isinstance(metadata.get(_MANUAL_SETTLEMENT_CAPTURE_KEY), dict)

    async def _lock_reservation_or_raise(self, db: AsyncSession, reservation_id: str):
        reservation = await self._reservation_repo.lock_by_id(db, reservation_id)
        if reservation is None:
            raise ValueError(f"Reservation {reservation_id} not found")
        return reservation

    def _terminal_result_if_blocked(
        self,
        reservation,
        *,
        treat_settlement_failed_as_terminal: bool = False,
    ) -> BillingSettlementResult | None:
        if reservation.status in _TERMINAL_STATUSES:
            return self._terminal_result(reservation)
        if (
            treat_settlement_failed_as_terminal
            and reservation.status == ReservationStatus.SETTLEMENT_FAILED
        ):
            return self._terminal_result(reservation)
        return None

    @staticmethod
    def _release_status_for_reason(reason: str) -> ReservationStatus:
        return (
            ReservationStatus.EXPIRED
            if reason == ReservationStatus.EXPIRED.value
            else ReservationStatus.RELEASED
        )

    async def _lock_balance_if_needed(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        needs_lock: bool,
    ) -> _CreditBuckets | None:
        if not needs_lock:
            return None
        balance = await self._balance_repo.lock_balance(db, user_id)
        if balance is None:
            raise ValueError(f"Balance not found for user {user_id}")
        return _CreditBuckets(
            regular=Decimal(str(balance[0])),
            bonus=Decimal(str(balance[1])),
        )

    @staticmethod
    def _reservation_buckets(reservation) -> _CreditBuckets:
        return _CreditBuckets(
            regular=Decimal(str(reservation.reserved_credits)),
            bonus=Decimal(str(reservation.reserved_bonus_credits)),
        )

    async def _release_reservation(
        self,
        db: AsyncSession,
        *,
        reservation,
        reason: str,
        target_status: ReservationStatus,
        actual_usd: Decimal | None = None,
        usage_payload: dict[str, Any] | None = None,
    ) -> BillingSettlementResult:
        reserved = self._reservation_buckets(reservation)
        release_ledger_id = await self._release_credits(
            db,
            user_id=reservation.user_id,
            source_domain=reservation.source_domain,
            source_id=reservation.source_id,
            credits=reserved.regular,
            bonus_credits=reserved.bonus,
            metadata=self._release_metadata(reservation, reason=reason),
            idempotency_key=self._derive_key(reservation.idempotency_key, "release"),
        )
        usage_record_id = await self._record_usage(
            db,
            reservation=reservation,
            amount=Decimal("0"),
            ledger_entry_id=reservation.reserve_ledger_entry_id,
            usage_payload=usage_payload,
            usage_metadata=self._build_usage_metadata(
                usage_payload=usage_payload,
                reservation=reservation,
                actual_requested_credits=Decimal("0"),
                settlement_status=target_status,
                released_credits=reserved.total,
            ),
            cost_usd=Decimal("0"),
        )

        reservation.status = target_status
        if release_ledger_id is not None:
            reservation.release_ledger_entry_id = release_ledger_id
        reservation.released_credits = reserved.regular
        reservation.released_bonus_credits = reserved.bonus
        reservation.last_error = None
        if actual_usd is not None:
            reservation.actual_credits = Decimal("0")
            reservation.actual_bonus_credits = Decimal("0")
            reservation.actual_usd = actual_usd
            reservation.usage_record_id = usage_record_id
        await db.flush()

        return BillingSettlementResult(
            reservation_id=reservation.id,
            status=target_status,
            released_credits=reserved.regular,
            released_bonus_credits=reserved.bonus,
            usage_record_id=usage_record_id,
        )

    @classmethod
    def _compute_settlement_breakdown(
        cls,
        *,
        reservation,
        actual_credits: Decimal,
    ) -> _SettlementBreakdown:
        reserved = cls._reservation_buckets(reservation)
        actual_bonus = min(reserved.bonus, actual_credits)
        remaining = actual_credits - actual_bonus
        actual_regular = min(reserved.regular, remaining)
        shortfall = remaining - actual_regular
        refund_regular = reserved.regular - actual_regular
        refund_bonus = reserved.bonus - actual_bonus
        return _SettlementBreakdown(
            reserved=reserved,
            actual_regular=actual_regular,
            actual_bonus=actual_bonus,
            refund_regular=refund_regular,
            refund_bonus=refund_bonus,
            shortfall=shortfall,
        )

    async def _refund_unused_credits(
        self,
        db: AsyncSession,
        *,
        reservation,
        breakdown: _SettlementBreakdown,
        locked_balance: _CreditBuckets | None,
    ) -> int | None:
        if breakdown.refund_regular <= 0 and breakdown.refund_bonus <= 0:
            return None
        return await self._release_credits(
            db,
            locked_balance=locked_balance,
            user_id=reservation.user_id,
            source_domain=reservation.source_domain,
            source_id=reservation.source_id,
            credits=breakdown.refund_regular,
            bonus_credits=breakdown.refund_bonus,
            metadata=self._release_metadata(
                reservation,
                reason=_LAST_ERROR_SETTLEMENT_REFUND,
            ),
            idempotency_key=self._derive_key(reservation.idempotency_key, "settlement-release"),
        )

    async def _charge_settlement_shortfall(
        self,
        db: AsyncSession,
        *,
        reservation,
        shortfall: Decimal,
        locked_balance: _CreditBuckets | None,
    ) -> _ShortfallOutcome:
        if shortfall <= 0:
            return _ShortfallOutcome()

        shortfall_key = self._derive_key(reservation.idempotency_key, "shortfall")
        if locked_balance is None:
            balance = await self._balance_repo.lock_balance(db, reservation.user_id)
            if balance is None:
                raise ValueError(f"Balance not found for user {reservation.user_id}")
            locked_balance = _CreditBuckets(
                regular=Decimal(str(balance[0])),
                bonus=Decimal(str(balance[1])),
            )

        shortfall_result = await self._credit_service.deduct_locked(
            db,
            reservation.user_id,
            float(shortfall),
            locked_balance=(locked_balance.regular, locked_balance.bonus),
            source_domain=reservation.source_domain,
            source_id=reservation.source_id,
            entry_metadata={
                "billing_context": reservation.billing_context,
                "billing_kind": reservation.billing_kind,
                "reservation_id": reservation.id,
                "settlement_shortfall": float(shortfall),
            },
            idempotency_key=shortfall_key,
            use_savepoint=False,
        )
        if shortfall_result is False:
            await self._mark_reconciliation_required(
                db,
                reservation.user_id,
                reason=(
                    f"Settlement shortfall for reservation {reservation.id}: "
                    f"needed {shortfall:.6f} credits"
                ),
            )
            return _ShortfallOutcome(
                settlement_status=ReservationStatus.SETTLEMENT_FAILED,
                shortfall_detected=True,
            )
        if shortfall_result is None:
            logger.info(
                "Shortfall deduction already applied for reservation %s "
                "(idempotency duplicate); proceeding with settlement",
                reservation.id,
            )
            return _ShortfallOutcome(shortfall_detected=True)

        assert isinstance(shortfall_result, CreditDeductionResult)
        return _ShortfallOutcome(
            charged_regular=abs(Decimal(str(shortfall_result.charged_credits))),
            charged_bonus=abs(Decimal(str(shortfall_result.charged_bonus_credits))),
            ledger_entry_id=shortfall_result.ledger_entry_id,
            shortfall_detected=True,
        )

    async def _record_settled_usage(
        self,
        db: AsyncSession,
        *,
        reservation,
        breakdown: _SettlementBreakdown,
        settlement_status: ReservationStatus,
        settled_total: Decimal,
        ledger_entry_id: int | None,
        usage_payload: dict[str, Any],
        actual_usd: Decimal,
    ) -> int | None:
        if settlement_status != ReservationStatus.SETTLED:
            return None
        return await self._record_usage(
            db,
            reservation=reservation,
            amount=settled_total,
            ledger_entry_id=ledger_entry_id,
            usage_payload=usage_payload,
            usage_metadata=self._build_usage_metadata(
                usage_payload=usage_payload,
                reservation=reservation,
                actual_requested_credits=breakdown.actual_requested,
                settlement_status=settlement_status,
                released_credits=breakdown.refund_regular + breakdown.refund_bonus,
            ),
            cost_usd=actual_usd,
        )

    async def _record_usage(
        self,
        db: AsyncSession,
        *,
        reservation,
        amount: Decimal,
        ledger_entry_id: int | None,
        usage_payload: dict[str, Any] | None,
        usage_metadata: dict[str, Any] | None,
        cost_usd: Decimal,
    ) -> int | None:
        if not usage_payload or usage_metadata is None:
            return None
        return await self._usage_service.record_settled_usage(
            db,
            user_id=reservation.user_id,
            billing_context=reservation.billing_context,
            subject_kind=reservation.subject_kind,
            subject_id=reservation.subject_id,
            run_id=reservation.run_id,
            amount=float(amount),
            source_domain=reservation.source_domain,
            billing_kind=reservation.billing_kind,
            model_id=reservation.model_id,
            tool_name=reservation.tool_name,
            ledger_entry_id=ledger_entry_id,
            usage_metadata=usage_metadata,
            provider=usage_payload.get("provider"),
            input_tokens=usage_payload.get("input_tokens", 0),
            output_tokens=usage_payload.get("output_tokens", 0),
            cache_read_tokens=usage_payload.get("cache_read_tokens", 0),
            cache_write_tokens=usage_payload.get("cache_write_tokens", 0),
            reasoning_tokens=usage_payload.get("reasoning_tokens", 0),
            latency_ms=usage_payload.get("latency_ms"),
            cost_usd=float(cost_usd),
            app_kind=usage_payload.get("app_kind"),
        )

    @staticmethod
    def _build_usage_metadata(
        *,
        usage_payload: dict[str, Any] | None,
        reservation,
        actual_requested_credits: Decimal,
        settlement_status: ReservationStatus,
        released_credits: Decimal,
    ) -> dict[str, Any] | None:
        if not usage_payload:
            return None
        reserved = CreditReservationService._reservation_buckets(reservation)
        return {
            **usage_payload,
            "reservation_id": reservation.id,
            "reserved_credits": float(reserved.total),
            "actual_requested_credits": float(actual_requested_credits),
            "settlement_status": settlement_status,
            "released_credits": float(released_credits),
        }

    @staticmethod
    def _release_metadata(reservation, *, reason: str) -> dict[str, Any]:
        return {
            "billing_context": reservation.billing_context,
            "billing_kind": reservation.billing_kind,
            "reason": reason,
            "reservation_id": reservation.id,
        }

    @staticmethod
    def _settlement_error(
        *,
        settlement_status: ReservationStatus,
        shortfall_detected: bool,
    ) -> str | None:
        if settlement_status == ReservationStatus.SETTLED:
            return None
        if shortfall_detected:
            return _LAST_ERROR_SHORTFALL
        return ReservationStatus.SETTLEMENT_FAILED.value

    def _apply_settlement_state(
        self,
        reservation,
        *,
        settlement_status: ReservationStatus,
        charged_regular: Decimal,
        charged_bonus: Decimal,
        refund_regular: Decimal,
        refund_bonus: Decimal,
        actual_usd: Decimal,
        usage_record_id: int | None,
        release_ledger_id: int | None,
        shortfall_ledger_id: int | None,
        shortfall_detected: bool,
    ) -> None:
        reservation.status = settlement_status
        if release_ledger_id is not None:
            reservation.release_ledger_entry_id = release_ledger_id
        reservation.shortfall_ledger_entry_id = shortfall_ledger_id
        reservation.actual_credits = charged_regular
        reservation.actual_bonus_credits = charged_bonus
        reservation.released_credits = refund_regular
        reservation.released_bonus_credits = refund_bonus
        reservation.actual_usd = actual_usd
        reservation.usage_record_id = usage_record_id
        reservation.last_error = self._settlement_error(
            settlement_status=settlement_status,
            shortfall_detected=shortfall_detected,
        )

    async def _release_credits(
        self,
        db: AsyncSession,
        *,
        locked_balance: _CreditBuckets | None = None,
        user_id: str,
        source_domain: str,
        source_id: str,
        credits: Decimal,
        bonus_credits: Decimal,
        metadata: dict[str, Any],
        idempotency_key: str | None,
    ) -> int | None:
        if credits <= 0 and bonus_credits <= 0:
            return None

        if locked_balance is None:
            balance = await self._balance_repo.lock_balance_state(db, user_id)
            if balance is None:
                raise ValueError(f"Balance not found for user {user_id}")
            locked_balance = _CreditBuckets(
                regular=Decimal(str(balance[0])),
                bonus=Decimal(str(balance[1])),
            )

        expected_credits_after = locked_balance.regular + credits
        expected_bonus_after = locked_balance.bonus + bonus_credits

        ledger_entry = await self._ledger_repo.append(
            db,
            user_id=user_id,
            entry_type=LedgerEntryType.RESERVATION_RELEASE,
            source_domain=source_domain,
            source_id=source_id,
            delta_credits=credits,
            delta_bonus_credits=bonus_credits,
            balance_after_credits=expected_credits_after,
            balance_after_bonus_credits=expected_bonus_after,
            entry_metadata=metadata,
            idempotency_key=idempotency_key,
        )
        if ledger_entry is None:
            return None

        new_values = await self._balance_repo.apply_delta_locked(
            db,
            user_id,
            delta_credits=credits,
            delta_bonus_credits=bonus_credits,
        )
        if new_values is None:
            raise ValueError("Failed to release reservation credits")
        return ledger_entry.id

    async def mark_settlement_failed(
        self,
        db: AsyncSession,
        *,
        reservation_id: str,
        error: str,
    ) -> None:
        """Transition a reservation to ``settlement_failed``.

        Called when the settle path raises after provider work was already
        completed.  The reservation must **not** be auto-expired (and thereby
        refunded) by the stale-expiry cron, because the user already received
        the paid output.  Moving it to ``settlement_failed`` excludes it from
        the ``list_stale_reserved`` query and leaves the captured settlement
        input available for manual replay.
        """
        async with db.begin_nested():
            reservation = await self._reservation_repo.lock_by_id(db, reservation_id)
            if reservation is None:
                return
            if reservation.status in _TERMINAL_STATUSES:
                return
            metadata = self._metadata_dict(reservation.reservation_metadata)
            capture = metadata.get(_MANUAL_SETTLEMENT_CAPTURE_KEY)
            if isinstance(capture, dict):
                capture["failed_at"] = datetime.now(timezone.utc).isoformat()
                capture["failure_error"] = error
                metadata[_MANUAL_SETTLEMENT_CAPTURE_KEY] = capture
                reservation.reservation_metadata = metadata
            reservation.status = ReservationStatus.SETTLEMENT_FAILED
            reservation.last_error = error
            await self._mark_reconciliation_required(
                db,
                reservation.user_id,
                reason=f"Settlement failed for reservation {reservation.id}: {error}",
            )
            await db.flush()

    async def _mark_reconciliation_required(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        reason: str,
    ) -> None:
        await self._balance_repo.set_billing_status(
            db,
            user_id,
            billing_status=BillingStatus.RECONCILIATION_REQUIRED,
            billing_status_reason=reason,
        )

    async def _maybe_clear_reconciliation_required(
        self,
        db: AsyncSession,
        *,
        user_id: str,
    ) -> None:
        if await self._reservation_repo.has_blocking_settlement_failures(db, user_id=user_id):
            return
        await self._balance_repo.set_billing_status(
            db,
            user_id,
            billing_status=BillingStatus.OK,
            billing_status_reason=None,
            expected_current_status=BillingStatus.RECONCILIATION_REQUIRED,
        )
