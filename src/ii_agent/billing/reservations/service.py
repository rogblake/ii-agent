"""Reservation service for prepaid LLM and tool billing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

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
    ReservationStatus,
)
from ii_agent.billing.exceptions import (
    BillingReconciliationRequiredError,
    InsufficientCreditsError,
)
from ii_agent.billing.usage.service import UsageService

logger = logging.getLogger(__name__)

# Terminal statuses — no further state transitions allowed.
_TERMINAL_STATUSES = frozenset({
    ReservationStatus.SETTLED,
    ReservationStatus.RELEASED,
    ReservationStatus.EXPIRED,
})

# last_error values for settle outcomes.
_LAST_ERROR_SHORTFALL = "settlement_shortfall_unreconciled"
_LAST_ERROR_SETTLEMENT_REFUND = "settlement_refund"


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
        source_domain: str,
        source_id: str,
        billing_kind: str,
        quote: BillingQuote,
        session_id: str | None = None,
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
        reserve_total = usd_to_credits(quote.reserve_usd)
        if reserve_total <= 0:
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
                raise BillingReconciliationRequiredError(
                    "Billing reconciliation required"
                )

            # Now check idempotency — under the balance lock, so no race.
            existing = await self._reservation_repo.get_by_idempotency_key(
                db, idempotency_key
            )
            if existing is not None:
                return self._build_hold(existing, output_token_cap=output_token_cap)

            if old_credits + old_bonus < reserve_total:
                raise InsufficientCreditsError(
                    "Insufficient credits",
                    phase="reserve",
                    available_credits=float(old_credits + old_bonus),
                    required_credits=float(reserve_total),
                )

            reserved_bonus = min(old_bonus, reserve_total)
            reserved_credits = reserve_total - reserved_bonus
            expected_credits_after = old_credits - reserved_credits
            expected_bonus_after = old_bonus - reserved_bonus
            entry_metadata = {
                **(metadata or {}),
                "billing_kind": billing_kind,
                "quote_strategy": quote.strategy,
                "quoted_usd": float(quote.reserve_usd),
                "max_usd": float(quote.max_usd),
                "reservation_source_id": source_id,
                "output_token_cap": output_token_cap,
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
                existing = await self._reservation_repo.get_by_idempotency_key(
                    db, idempotency_key
                )
                if existing is not None:
                    return self._build_hold(existing, output_token_cap=output_token_cap)
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
                session_id=session_id,
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
                },
                expires_at=expires_at,
            )

        return self._build_hold(reservation, output_token_cap=output_token_cap)

    async def release(
        self,
        db: AsyncSession,
        *,
        reservation_id: str,
        reason: str,
    ) -> BillingSettlementResult:
        """Release a reservation when work did not produce a billable result."""
        async with db.begin_nested():
            reservation = await self._reservation_repo.lock_by_id(db, reservation_id)
            if reservation is None:
                raise ValueError(f"Reservation {reservation_id} not found")

            # Guard terminal statuses and SETTLEMENT_FAILED — work was
            # already delivered so credits must not be refunded.
            if (
                reservation.status in _TERMINAL_STATUSES
                or reservation.status == ReservationStatus.SETTLEMENT_FAILED
            ):
                return self._terminal_result(reservation)

            release_idempotency_key = self._derive_key(
                reservation.idempotency_key, "release"
            )
            release_ledger_id = await self._release_split(
                db,
                user_id=reservation.user_id,
                source_domain=reservation.source_domain,
                source_id=reservation.source_id,
                credits=Decimal(str(reservation.reserved_credits)),
                bonus_credits=Decimal(str(reservation.reserved_bonus_credits)),
                metadata={
                    "billing_kind": reservation.billing_kind,
                    "reason": reason,
                    "reservation_id": reservation.id,
                },
                idempotency_key=release_idempotency_key,
            )

            target_status = (
                ReservationStatus.EXPIRED
                if reason == ReservationStatus.EXPIRED.value
                else ReservationStatus.RELEASED
            )
            reservation.status = target_status
            reservation.release_ledger_entry_id = release_ledger_id
            reservation.released_credits = reservation.reserved_credits
            reservation.released_bonus_credits = reservation.reserved_bonus_credits
            reservation.last_error = None
            await db.flush()

        return BillingSettlementResult(
            reservation_id=reservation.id,
            status=target_status,
            released_credits=Decimal(str(reservation.reserved_credits)),
            released_bonus_credits=Decimal(str(reservation.reserved_bonus_credits)),
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
            reservation = await self._reservation_repo.lock_by_id(db, reservation_id)
            if reservation is None:
                raise ValueError(f"Reservation {reservation_id} not found")

            # Guard all terminal statuses — no re-processing.
            if reservation.status in _TERMINAL_STATUSES:
                return self._terminal_result(reservation)

            # Zero-cost settle → inline release (avoid nested savepoint).
            if actual_credits <= 0:
                release_idempotency_key = self._derive_key(
                    reservation.idempotency_key, "release"
                )
                release_ledger_id = await self._release_split(
                    db,
                    user_id=reservation.user_id,
                    source_domain=reservation.source_domain,
                    source_id=reservation.source_id,
                    credits=Decimal(str(reservation.reserved_credits)),
                    bonus_credits=Decimal(str(reservation.reserved_bonus_credits)),
                    metadata={
                        "billing_kind": reservation.billing_kind,
                        "reason": "unused",
                        "reservation_id": reservation.id,
                    },
                    idempotency_key=release_idempotency_key,
                )
                reservation.status = ReservationStatus.RELEASED
                reservation.release_ledger_entry_id = release_ledger_id
                reservation.released_credits = reservation.reserved_credits
                reservation.released_bonus_credits = reservation.reserved_bonus_credits
                reservation.actual_credits = Decimal("0")
                reservation.actual_bonus_credits = Decimal("0")
                reservation.actual_usd = actual_usd
                reservation.last_error = None
                await db.flush()

                return BillingSettlementResult(
                    reservation_id=reservation.id,
                    status=ReservationStatus.RELEASED,
                    released_credits=Decimal(str(reservation.reserved_credits)),
                    released_bonus_credits=Decimal(str(reservation.reserved_bonus_credits)),
                )

            reserved_regular = Decimal(str(reservation.reserved_credits))
            reserved_bonus = Decimal(str(reservation.reserved_bonus_credits))
            actual_bonus = min(reserved_bonus, actual_credits)
            remaining = actual_credits - actual_bonus
            actual_regular = min(reserved_regular, remaining)
            remaining -= actual_regular

            refund_regular = reserved_regular - actual_regular
            refund_bonus = reserved_bonus - actual_bonus
            release_ledger_id: int | None = None
            if refund_regular > 0 or refund_bonus > 0:
                settle_release_key = self._derive_key(
                    reservation.idempotency_key, "settlement-release"
                )
                release_ledger_id = await self._release_split(
                    db,
                    user_id=reservation.user_id,
                    source_domain=reservation.source_domain,
                    source_id=reservation.source_id,
                    credits=refund_regular,
                    bonus_credits=refund_bonus,
                    metadata={
                        "billing_kind": reservation.billing_kind,
                        "reason": _LAST_ERROR_SETTLEMENT_REFUND,
                        "reservation_id": reservation.id,
                    },
                    idempotency_key=settle_release_key,
                )

            shortfall_regular = Decimal("0")
            shortfall_bonus = Decimal("0")
            shortfall_ledger_id: int | None = None
            settlement_status = ReservationStatus.SETTLED
            shortfall_detected = remaining > 0

            if remaining > 0:
                shortfall_key = self._derive_key(
                    reservation.idempotency_key, "shortfall"
                )
                shortfall_result = await self._credit_service.deduct(
                    db,
                    reservation.user_id,
                    float(remaining),
                    source_domain=reservation.source_domain,
                    source_id=reservation.source_id,
                    entry_metadata={
                        "billing_kind": reservation.billing_kind,
                        "reservation_id": reservation.id,
                        "settlement_shortfall": float(remaining),
                    },
                    idempotency_key=shortfall_key,
                )

                if shortfall_result is False:
                    await self._mark_reconciliation_required(
                        db,
                        reservation.user_id,
                        reason=(
                            f"Settlement shortfall for reservation {reservation.id}: "
                            f"needed {remaining:.6f} credits"
                        ),
                    )
                    settlement_status = ReservationStatus.SETTLEMENT_FAILED
                elif shortfall_result is None:
                    # Idempotency duplicate — shortfall was already charged
                    # in a prior settlement attempt.  Log and continue so the
                    # reservation transitions to SETTLED instead of being
                    # incorrectly blocked as SETTLEMENT_FAILED.
                    logger.info(
                        "Shortfall deduction already applied for reservation %s "
                        "(idempotency duplicate); proceeding with settlement",
                        reservation.id,
                    )
                else:
                    assert isinstance(shortfall_result, CreditDeductionResult)
                    shortfall_ledger_id = shortfall_result.ledger_entry_id
                    shortfall_regular = abs(
                        Decimal(str(shortfall_result.charged_credits))
                    )
                    shortfall_bonus = abs(
                        Decimal(str(shortfall_result.charged_bonus_credits))
                    )

            total_regular = actual_regular + shortfall_regular
            total_bonus = actual_bonus + shortfall_bonus
            settled_total = total_regular + total_bonus

            usage_record_id: int | None = None
            if settled_total > 0 and settlement_status == ReservationStatus.SETTLED:
                usage_metadata = {
                    **usage_payload,
                    "reservation_id": reservation.id,
                    "reserved_credits": float(reserved_regular + reserved_bonus),
                    "actual_requested_credits": float(actual_credits),
                    "settlement_status": settlement_status,
                    "released_credits": float(refund_regular + refund_bonus),
                }
                usage_record_id = await self._usage_service.record_settled_usage(
                    db,
                    user_id=reservation.user_id,
                    session_id=reservation.session_id,
                    run_id=reservation.run_id,
                    amount=float(settled_total),
                    source_domain=reservation.source_domain,
                    billing_kind=reservation.billing_kind,
                    model_id=reservation.model_id,
                    tool_name=reservation.tool_name,
                    ledger_entry_id=(
                        shortfall_ledger_id or reservation.reserve_ledger_entry_id
                    ),
                    usage_metadata=usage_metadata,
                    provider=usage_payload.get("provider"),
                    input_tokens=usage_payload.get("input_tokens", 0),
                    output_tokens=usage_payload.get("output_tokens", 0),
                    cache_read_tokens=usage_payload.get("cache_read_tokens", 0),
                    cache_write_tokens=usage_payload.get("cache_write_tokens", 0),
                    reasoning_tokens=usage_payload.get("reasoning_tokens", 0),
                    latency_ms=usage_payload.get("latency_ms"),
                    cost_usd=float(actual_usd),
                    app_kind=usage_payload.get("app_kind"),
                )

            reservation.status = settlement_status
            reservation.release_ledger_entry_id = release_ledger_id
            reservation.shortfall_ledger_entry_id = shortfall_ledger_id
            reservation.actual_credits = total_regular
            reservation.actual_bonus_credits = total_bonus
            reservation.released_credits = refund_regular
            reservation.released_bonus_credits = refund_bonus
            reservation.actual_usd = actual_usd
            reservation.usage_record_id = usage_record_id
            reservation.last_error = (
                None
                if settlement_status == ReservationStatus.SETTLED
                else (
                    _LAST_ERROR_SHORTFALL
                    if shortfall_detected
                    else ReservationStatus.SETTLEMENT_FAILED.value
                )
            )
            await db.flush()

        return BillingSettlementResult(
            reservation_id=reservation.id,
            status=settlement_status,  # type: ignore[arg-type]
            charged_credits=total_regular,
            charged_bonus_credits=total_bonus,
            released_credits=refund_regular,
            released_bonus_credits=refund_bonus,
            usage_record_id=usage_record_id,
            shortfall_detected=shortfall_detected,
        )

    async def expire_stale(
        self,
        db: AsyncSession,
        *,
        older_than: datetime,
        limit: int = 100,
    ) -> int:
        """Expire and release old reservations."""
        stale = await self._reservation_repo.list_stale_reserved(
            db, older_than=older_than, limit=limit
        )
        for reservation in stale:
            await self.release(
                db,
                reservation_id=reservation.id,
                reason=ReservationStatus.EXPIRED.value,
            )
        return len(stale)

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
            charged_bonus_credits=Decimal(
                str(reservation.actual_bonus_credits or 0)
            ),
            released_credits=Decimal(str(reservation.released_credits or 0)),
            released_bonus_credits=Decimal(
                str(reservation.released_bonus_credits or 0)
            ),
            usage_record_id=reservation.usage_record_id,
        )

    def _build_hold(
        self,
        reservation,
        *,
        output_token_cap: int | None,
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
        )

    async def _release_split(
        self,
        db: AsyncSession,
        *,
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

        balance = await self._balance_repo.lock_balance_state(db, user_id)
        if balance is None:
            raise ValueError(f"Balance not found for user {user_id}")

        old_credits, old_bonus, _status = balance
        expected_credits_after = old_credits + credits
        expected_bonus_after = old_bonus + bonus_credits

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
        the ``list_stale_reserved`` query while still allowing a later retry
        from the durable billing outbox.
        """
        async with db.begin_nested():
            reservation = await self._reservation_repo.lock_by_id(
                db, reservation_id
            )
            if reservation is None:
                return
            if reservation.status in _TERMINAL_STATUSES:
                return
            reservation.status = ReservationStatus.SETTLEMENT_FAILED
            reservation.last_error = error
            await db.flush()

    async def _mark_reconciliation_required(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        reason: str,
    ) -> None:
        balance = await self._balance_repo.lock_balance_state(db, user_id)
        if balance is None:
            return
        await self._balance_repo.apply_delta_locked(
            db,
            user_id,
            delta_credits=Decimal("0"),
            delta_bonus_credits=Decimal("0"),
            billing_status=BillingStatus.RECONCILIATION_REQUIRED,
            billing_status_reason=reason,
        )
