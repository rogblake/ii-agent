"""Billing usage fact capture and retry processing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.credits.pricing import ModelPricing
from ii_agent.billing.credits.utils import usd_to_credits
from ii_agent.billing.outbox.models import BillingUsageFact
from ii_agent.billing.outbox.repository import BillingUsageFactRepository
from ii_agent.billing.reservations.repository import CreditReservationRepository
from ii_agent.billing.reservations.service import CreditReservationService
from ii_agent.billing.reservations.types import (
    BillingKind,
    BillingSettlementResult,
    ReservationStatus,
)
from ii_agent.core.llm.token_record import TokenRecord

if TYPE_CHECKING:
    from ii_agent.core.llm.billing_service import ReservedLLMCall

logger = logging.getLogger(__name__)

_STATUS_CAPTURED = "captured"
_STATUS_PROCESSING = "processing"
_STATUS_PROCESSED = "processed"
_STATUS_MANUAL_REVIEW = "manual_review"
_MAX_ATTEMPTS = 5


class BillingUsageFactService:
    """Persist exact invocation facts and retry billing from them."""

    def __init__(
        self,
        *,
        repository: BillingUsageFactRepository,
        reservation_repository: CreditReservationRepository,
        reservation_service: CreditReservationService,
    ) -> None:
        self._repository = repository
        self._reservation_repository = reservation_repository
        self._reservation_service = reservation_service

    async def capture_llm_fact(
        self,
        db: AsyncSession,
        *,
        reservation: "ReservedLLMCall | None",
        user_id: str | None,
        session_id: str | None,
        run_id: str | None,
        message_id: str | None = None,
        app_kind: str,
        provider: str | None,
        request_kind: str | None,
        token_record: TokenRecord,
        latency_ms: int | None = None,
    ) -> BillingUsageFact | None:
        """Persist one LLM invocation fact keyed by reservation id."""
        if reservation is None:
            return None
        user_id, session_id = await self._resolve_context(
            db,
            reservation_id=reservation.hold.reservation_id,
            user_id=user_id,
            session_id=session_id,
        )

        return await self._repository.insert_idempotent(
            db,
            reservation_id=reservation.hold.reservation_id,
            user_id=user_id,
            session_id=session_id,
            run_id=run_id,
            message_id=message_id,
            billing_kind=BillingKind.LLM_USAGE,
            event_kind="llm",
            app_kind=app_kind,
            provider=provider,
            request_kind=request_kind,
            model_id=token_record.model_id or reservation.pricing.model_id,
            prompt_tokens=token_record.input_tokens,
            completion_tokens=token_record.output_tokens,
            cache_read_tokens=token_record.cache_read_tokens,
            cache_write_tokens=token_record.cache_write_tokens,
            reasoning_tokens=token_record.reasoning_tokens,
            latency_ms=latency_ms,
            cost_usd=token_record.direct_cost,
        )

    async def capture_tool_fact(
        self,
        db: AsyncSession,
        *,
        reservation_id: str,
        user_id: str | None,
        session_id: str | None,
        run_id: str | None,
        message_id: str | None = None,
        app_kind: str | None,
        tool_name: str,
        provider: str | None,
        actual_cost_usd: float,
        latency_ms: int | None = None,
    ) -> BillingUsageFact:
        """Persist one tool invocation fact keyed by reservation id."""
        user_id, session_id = await self._resolve_context(
            db,
            reservation_id=reservation_id,
            user_id=user_id,
            session_id=session_id,
        )
        return await self._repository.insert_idempotent(
            db,
            reservation_id=reservation_id,
            user_id=user_id,
            session_id=session_id,
            run_id=run_id,
            message_id=message_id,
            billing_kind=BillingKind.TOOL_USAGE,
            event_kind="tool",
            app_kind=app_kind,
            provider=provider,
            tool_name=tool_name,
            latency_ms=latency_ms,
            cost_usd=max(actual_cost_usd, 0.0),
        )

    async def process_fact(
        self,
        db: AsyncSession,
        *,
        fact_id: int,
    ) -> BillingSettlementResult | None:
        """Apply one captured fact to its reservation."""
        fact = await self._repository.lock_by_id(db, fact_id)
        if fact is None:
            return None
        return await self._process_locked_fact(db, fact)

    async def retry_dispatchable(
        self,
        db: AsyncSession,
        *,
        limit: int = 50,
        stale_after: timedelta = timedelta(minutes=10),
    ) -> int:
        """Retry captured or stale-processing facts in the current transaction."""
        stale_before = datetime.now(timezone.utc) - stale_after
        facts = await self._repository.list_dispatchable_locked(
            db,
            stale_before=stale_before,
            limit=limit,
        )
        processed = 0
        for fact in facts:
            try:
                await self._process_locked_fact(db, fact)
            except Exception:
                logger.error(
                    "Failed to process billing usage fact %s",
                    fact.id,
                    exc_info=True,
                )
            processed += 1
        return processed

    async def _process_locked_fact(
        self,
        db: AsyncSession,
        fact: BillingUsageFact,
    ) -> BillingSettlementResult | None:
        if fact.status == _STATUS_MANUAL_REVIEW:
            return None

        now = datetime.now(timezone.utc)
        if fact.status != _STATUS_PROCESSED:
            fact.status = _STATUS_PROCESSING
            fact.processing_started_at = now
            fact.attempt_count = int(fact.attempt_count or 0) + 1
            fact.last_error = None
            await db.flush()

        try:
            result = await self._apply_fact(db, fact)
        except Exception as exc:
            await self._reservation_service.mark_settlement_failed(
                db,
                reservation_id=fact.reservation_id,
                error=str(exc),
            )
            fact.failed_at = now
            fact.processing_started_at = None
            fact.last_error = str(exc)
            fact.status = (
                _STATUS_MANUAL_REVIEW
                if int(fact.attempt_count or 0) >= _MAX_ATTEMPTS
                else _STATUS_CAPTURED
            )
            await db.flush()
            raise

        if result.status == ReservationStatus.SETTLEMENT_FAILED:
            fact.failed_at = now
            fact.processing_started_at = None
            fact.last_error = ReservationStatus.SETTLEMENT_FAILED.value
            fact.status = (
                _STATUS_MANUAL_REVIEW
                if int(fact.attempt_count or 0) >= _MAX_ATTEMPTS
                else _STATUS_CAPTURED
            )
            await db.flush()
            return result

        fact.status = _STATUS_PROCESSED
        fact.charged_credits = (
            Decimal(str(result.total_charged))
            if result is not None
            else None
        )
        fact.processed_at = now
        fact.processing_started_at = None
        fact.last_error = None
        await db.flush()
        return result

    async def _apply_fact(
        self,
        db: AsyncSession,
        fact: BillingUsageFact,
    ) -> BillingSettlementResult:
        if fact.event_kind == "tool":
            actual_usd = Decimal(str(fact.cost_usd or 0))
            actual_credits = usd_to_credits(actual_usd)
            return await self._reservation_service.settle(
                db,
                reservation_id=fact.reservation_id,
                actual_credits=actual_credits,
                actual_usd=actual_usd,
                usage_payload={
                    "app_kind": fact.app_kind,
                    "run_id": str(fact.run_id) if fact.run_id is not None else None,
                    "provider": fact.provider,
                    "tool_name": fact.tool_name,
                    "latency_ms": fact.latency_ms,
                    "cost_usd": float(actual_usd),
                },
            )

        if fact.event_kind != "llm":
            raise ValueError(f"Unknown billing fact type: {fact.event_kind}")

        model_id = fact.model_id or ""
        pricing = ModelPricing.get_default_pricing(
            model_id,
            provider=self._provider_from_fact(fact.provider),
        )
        record = TokenRecord(
            input_tokens=fact.prompt_tokens,
            output_tokens=fact.completion_tokens,
            cache_read_tokens=fact.cache_read_tokens,
            cache_write_tokens=fact.cache_write_tokens,
            reasoning_tokens=fact.reasoning_tokens,
            model_id=model_id,
            direct_cost=float(fact.cost_usd or 0),
        )
        actual_usd = self._calculate_llm_usd(record, pricing)
        actual_credits = usd_to_credits(actual_usd)
        return await self._reservation_service.settle(
            db,
            reservation_id=fact.reservation_id,
            actual_credits=actual_credits,
            actual_usd=actual_usd,
            usage_payload={
                "app_kind": fact.app_kind,
                "run_id": str(fact.run_id) if fact.run_id is not None else None,
                "provider": fact.provider,
                "request_kind": fact.request_kind,
                "input_tokens": fact.prompt_tokens,
                "output_tokens": fact.completion_tokens,
                "cache_read_tokens": fact.cache_read_tokens,
                "cache_write_tokens": fact.cache_write_tokens,
                "reasoning_tokens": fact.reasoning_tokens,
                "latency_ms": fact.latency_ms,
                "direct_cost_usd": float(fact.cost_usd or 0),
            },
        )

    @staticmethod
    def _calculate_llm_usd(record: TokenRecord, pricing: ModelPricing) -> Decimal:
        """Compute USD cost in Decimal to avoid float precision loss."""
        _M = Decimal("1000000")
        return (
            Decimal(record.input_tokens) * Decimal(str(pricing.input_price_per_million)) / _M
            + Decimal(record.output_tokens) * Decimal(str(pricing.output_price_per_million)) / _M
            + Decimal(record.cache_write_tokens) * Decimal(str(pricing.cache_write_price_per_million)) / _M
            + Decimal(record.cache_read_tokens) * Decimal(str(pricing.cache_read_price_per_million)) / _M
            + Decimal(str(record.direct_cost))
        )

    async def _resolve_context(
        self,
        db: AsyncSession,
        *,
        reservation_id: str,
        user_id: str | None,
        session_id: str | None,
    ) -> tuple[str, str | None]:
        if user_id:
            return user_id, session_id

        reservation = await self._reservation_repository.get_by_id(
            db,
            reservation_id=reservation_id,
        )
        if reservation is None:
            raise ValueError(f"Reservation {reservation_id} not found")
        return reservation.user_id, session_id or reservation.session_id

    @staticmethod
    def _provider_from_fact(provider: str | None):
        from ii_agent.agent.types import Provider

        mapping = {
            "anthropic": Provider.ANTHROPIC,
            "openai": Provider.OPENAI,
            "gemini": Provider.GOOGLE,
            "google": Provider.GOOGLE,
        }
        return mapping.get(str(provider).lower()) if provider else None
