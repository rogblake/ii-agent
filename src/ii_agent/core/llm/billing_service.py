"""Centralized LLM and tool billing for chat and agent runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
import logging
import math
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.credits.pricing import ModelPricing
from ii_agent.billing.credits.service import CreditService
from ii_agent.billing.credits.utils import credits_to_usd, usd_to_credits
from ii_agent.billing.reservations.service import CreditReservationService
from ii_agent.billing.reservations.types import (
    BillingKind,
    BillingQuote,
    BillingSettlementResult,
    QuoteStrategy,
    ReservationHold,
    SourceDomain,
)
from ii_agent.billing.exceptions import InsufficientCreditsError
from ii_agent.core.llm.token_record import TokenRecord

_MIN_USEFUL_OUTPUT_TOKENS = 128

if TYPE_CHECKING:
    from ii_agent.agent.runtime.models.base import Model
    from ii_agent.billing.outbox.service import BillingUsageFactService
    from ii_agent.billing.usage.service import UsageService
    from ii_agent.core.config.llm_config import APITypes, LLMConfig
    from ii_agent.core.config.settings import Settings

logger = logging.getLogger(__name__)

try:
    import tiktoken

    _ENCODING = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover - tokenizer import failure should not block runtime
    _ENCODING = None


@dataclass(frozen=True)
class ReservedLLMCall:
    """Reservation handle for one LLM call."""

    hold: ReservationHold
    input_tokens_estimate: int
    output_token_cap: int
    pricing: ModelPricing
    provider_options: dict[str, Any] | None = None


@dataclass(frozen=True)
class ReservedToolCall:
    """Reservation handle for one tool call."""

    hold: ReservationHold
    quote: BillingQuote


class LLMBillingService:
    """Calculate prices and coordinate reserve/settle/release flows."""

    def __init__(
        self,
        *,
        usage_service: UsageService,
        credit_service: CreditService,
        reservation_service: CreditReservationService,
        config: Settings,
        outbox_service: BillingUsageFactService | None = None,
    ) -> None:
        self._usage_service = usage_service
        self._credit_service = credit_service
        self._reservation_service = reservation_service
        self._config = config
        self._outbox_service = outbox_service

    # ------------------------------------------------------------------
    # Reservation API
    # ------------------------------------------------------------------

    async def reserve_chat_llm_call(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        session_id: str,
        run_id: str,
        model_id: str,
        llm_config: LLMConfig,
        messages: list[Any],
        source_id: str,
        idempotency_key: str,
        request_kind: str,
    ) -> ReservedLLMCall | None:
        """Reserve one chat LLM call before sending it to the provider."""
        if llm_config.is_user_model():
            return None

        input_tokens = self.estimate_tokens(messages)
        pricing = ModelPricing.get_default_pricing(
            model_id,
            provider=self._provider_from_api_type(llm_config.api_type),
        )
        quote, output_cap = await self._quote_llm_call(
            db,
            user_id=user_id,
            model_id=model_id,
            pricing=pricing,
            input_tokens=input_tokens,
            model_cap=self._chat_model_output_cap(llm_config=llm_config),
        )
        hold = await self._reservation_service.reserve(
            db,
            user_id=user_id,
            session_id=session_id,
            run_id=run_id,
            source_domain=SourceDomain.CHAT_LLM,
            source_id=source_id,
            billing_kind=BillingKind.LLM_USAGE,
            quote=quote,
            model_id=model_id,
            idempotency_key=idempotency_key,
            metadata={
                "app_kind": "chat",
                "request_kind": request_kind,
                "input_tokens_estimate": input_tokens,
            },
            output_token_cap=output_cap,
        )
        if hold is None:
            return None
        return ReservedLLMCall(
            hold=hold,
            input_tokens_estimate=input_tokens,
            output_token_cap=output_cap,
            pricing=pricing,
            provider_options=self.build_chat_provider_options(
                llm_config=llm_config,
                output_token_cap=output_cap,
            ),
        )

    async def settle_chat_llm_call(
        self,
        db: AsyncSession,
        *,
        reservation: ReservedLLMCall | None,
        user_id: str,
        session_id: str,
        run_id: str,
        token_record: TokenRecord,
        provider: str | None,
        request_kind: str,
        latency_ms: int | None = None,
    ) -> BillingSettlementResult | None:
        """Settle a chat LLM reservation to actual provider usage."""
        if reservation is None:
            return None

        if self._outbox_service is None:
            return await self._settle_llm_direct(
                db,
                reservation_id=reservation.hold.reservation_id,
                pricing=reservation.pricing,
                token_record=token_record,
                app_kind="chat",
                run_id=run_id,
                provider=provider,
                request_kind=request_kind,
                latency_ms=latency_ms,
            )

        fact = await self._outbox_service.capture_llm_fact(
            db,
            reservation=reservation,
            user_id=user_id,
            session_id=session_id,
            run_id=run_id,
            app_kind="chat",
            provider=provider,
            request_kind=request_kind,
            token_record=token_record,
            latency_ms=latency_ms,
        )
        return await self._outbox_service.process_fact(db, fact_id=fact.id)

    async def reserve_agent_llm_call(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        session_id: str,
        run_id: str,
        model: Model,
        messages: list[Any],
        source_id: str,
        idempotency_key: str,
    ) -> ReservedLLMCall | None:
        """Reserve one agent model invocation before it starts."""
        if not model.bill_with_platform_credits:
            return None

        input_tokens = self.estimate_tokens(messages)
        pricing = ModelPricing.get_default_pricing(model.id, provider=model.provider)
        quote, output_cap = await self._quote_llm_call(
            db,
            user_id=user_id,
            model_id=model.id,
            pricing=pricing,
            input_tokens=input_tokens,
            model_cap=self._agent_model_output_cap(model),
        )
        hold = await self._reservation_service.reserve(
            db,
            user_id=user_id,
            session_id=session_id,
            run_id=run_id,
            source_domain=SourceDomain.AGENT_LLM,
            source_id=source_id,
            billing_kind=BillingKind.LLM_USAGE,
            quote=quote,
            model_id=model.id,
            idempotency_key=idempotency_key,
            metadata={
                "app_kind": "agent",
                "input_tokens_estimate": input_tokens,
            },
            output_token_cap=output_cap,
        )
        if hold is None:
            return None
        return ReservedLLMCall(
            hold=hold,
            input_tokens_estimate=input_tokens,
            output_token_cap=output_cap,
            pricing=pricing,
        )

    async def settle_agent_llm_call(
        self,
        db: AsyncSession,
        *,
        reservation: ReservedLLMCall | None,
        run_id: str,
        token_record: TokenRecord,
        provider: str | None,
        latency_ms: int | None = None,
    ) -> BillingSettlementResult | None:
        """Settle one agent model invocation."""
        if reservation is None:
            return None

        if self._outbox_service is None:
            return await self._settle_llm_direct(
                db,
                reservation_id=reservation.hold.reservation_id,
                pricing=reservation.pricing,
                token_record=token_record,
                app_kind="agent",
                run_id=run_id,
                provider=provider,
                request_kind=None,
                latency_ms=latency_ms,
            )

        fact = await self._outbox_service.capture_llm_fact(
            db,
            reservation=reservation,
            user_id=None,
            session_id=None,
            run_id=run_id,
            app_kind="agent",
            provider=provider,
            request_kind=None,
            token_record=token_record,
            latency_ms=latency_ms,
        )
        return await self._outbox_service.process_fact(db, fact_id=fact.id)

    async def release_llm_call(
        self,
        db: AsyncSession,
        *,
        reservation: ReservedLLMCall | None,
        reason: str,
    ) -> BillingSettlementResult | None:
        """Release an LLM reservation without charging usage."""
        if reservation is None:
            return None
        return await self._reservation_service.release(
            db,
            reservation_id=reservation.hold.reservation_id,
            reason=reason,
        )

    async def mark_settlement_failed(
        self,
        db: AsyncSession,
        *,
        reservation_id: str,
        error: str,
    ) -> None:
        """Mark a reservation as settlement_failed after a settle exception."""
        await self._reservation_service.mark_settlement_failed(
            db,
            reservation_id=reservation_id,
            error=error,
        )

    async def reserve_tool_call(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        session_id: str,
        run_id: str | None,
        source_domain: str,
        source_id: str,
        tool_name: str,
        quote: BillingQuote | None,
        idempotency_key: str,
        app_kind: str,
    ) -> ReservedToolCall | None:
        """Reserve one billable tool call before execution."""
        if quote is None:
            return None
        if quote.strategy == QuoteStrategy.POST_FACTO:
            raise ValueError(f"Tool {tool_name} must provide an exact or bounded upfront quote")

        hold = await self._reservation_service.reserve(
            db,
            user_id=user_id,
            session_id=session_id,
            run_id=run_id,
            source_domain=source_domain,
            source_id=source_id,
            billing_kind=BillingKind.TOOL_USAGE,
            quote=quote,
            tool_name=tool_name,
            idempotency_key=idempotency_key,
            metadata={
                "app_kind": app_kind,
                "tool_name": tool_name,
            },
        )
        if hold is None:
            return None
        return ReservedToolCall(hold=hold, quote=quote)

    async def settle_tool_call(
        self,
        db: AsyncSession,
        *,
        reservation: ReservedToolCall | None,
        actual_cost_usd: float,
        provider: str | None,
        latency_ms: int | None = None,
        extra_usage_metadata: dict[str, Any] | None = None,
    ) -> BillingSettlementResult | None:
        """Settle one reserved tool call to its final direct cost."""
        if reservation is None:
            return None
        return await self.settle_tool_call_by_reservation_id(
            db,
            reservation_id=reservation.hold.reservation_id,
            actual_cost_usd=actual_cost_usd,
            provider=provider,
            latency_ms=latency_ms,
            extra_usage_metadata=extra_usage_metadata,
        )

    async def release_tool_call(
        self,
        db: AsyncSession,
        *,
        reservation: ReservedToolCall | None,
        reason: str,
    ) -> BillingSettlementResult | None:
        """Release a tool reservation without charging."""
        if reservation is None:
            return None
        return await self.release_tool_call_by_reservation_id(
            db,
            reservation_id=reservation.hold.reservation_id,
            reason=reason,
        )

    async def settle_tool_call_by_reservation_id(
        self,
        db: AsyncSession,
        *,
        reservation_id: str,
        actual_cost_usd: float,
        provider: str | None,
        latency_ms: int | None = None,
        extra_usage_metadata: dict[str, Any] | None = None,
    ) -> BillingSettlementResult:
        """Settle one tool reservation by its persisted reservation id."""
        if self._outbox_service is not None:
            fact = await self._outbox_service.capture_tool_fact(
                db,
                reservation_id=reservation_id,
                user_id=(
                    str(extra_usage_metadata.get("user_id"))
                    if extra_usage_metadata and extra_usage_metadata.get("user_id")
                    else None
                ),
                session_id=(
                    str(extra_usage_metadata.get("session_id"))
                    if extra_usage_metadata and extra_usage_metadata.get("session_id")
                    else None
                ),
                run_id=(
                    str(extra_usage_metadata.get("run_id"))
                    if extra_usage_metadata and extra_usage_metadata.get("run_id")
                    else None
                ),
                app_kind=(
                    str(extra_usage_metadata.get("app_kind"))
                    if extra_usage_metadata and extra_usage_metadata.get("app_kind")
                    else None
                ),
                tool_name=(
                    str(extra_usage_metadata.get("tool_name"))
                    if extra_usage_metadata and extra_usage_metadata.get("tool_name")
                    else "tool"
                ),
                provider=provider,
                actual_cost_usd=actual_cost_usd,
                latency_ms=latency_ms,
            )
            return await self._outbox_service.process_fact(db, fact_id=fact.id)

        return await self._settle_tool_direct(
            db,
            reservation_id=reservation_id,
            actual_cost_usd=actual_cost_usd,
            provider=provider,
            latency_ms=latency_ms,
            extra_usage_metadata=extra_usage_metadata,
        )

    async def retry_captured_usage_facts(
        self,
        db: AsyncSession,
        *,
        limit: int = 50,
    ) -> int:
        """Retry captured/stale billing facts from the durable outbox."""
        if self._outbox_service is None:
            return 0
        return await self._outbox_service.retry_dispatchable(
            db,
            limit=limit,
        )

    async def _settle_llm_direct(
        self,
        db: AsyncSession,
        *,
        reservation_id: str,
        pricing: ModelPricing,
        token_record: TokenRecord,
        app_kind: str,
        run_id: str,
        provider: str | None,
        request_kind: str | None,
        latency_ms: int | None,
    ) -> BillingSettlementResult:
        actual_usd = self._calculate_usd(token_record, pricing)
        actual_credits = self._calculate(token_record, pricing)
        return await self._reservation_service.settle(
            db,
            reservation_id=reservation_id,
            actual_credits=actual_credits,
            actual_usd=actual_usd,
            usage_payload={
                "app_kind": app_kind,
                "run_id": run_id,
                "provider": provider,
                "request_kind": request_kind,
                "input_tokens": token_record.input_tokens,
                "output_tokens": token_record.output_tokens,
                "cache_read_tokens": token_record.cache_read_tokens,
                "cache_write_tokens": token_record.cache_write_tokens,
                "reasoning_tokens": token_record.reasoning_tokens,
                "latency_ms": latency_ms,
                "direct_cost_usd": token_record.direct_cost,
            },
        )

    async def record_zero_cost_tool_usage(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        session_id: str,
        run_id: str | None,
        tool_name: str,
        succeeded: bool,
        app_kind: str = "agent",
    ) -> int | None:
        """Record a usage record for a tool that has no billing cost."""
        return await self._usage_service.record_settled_usage(
            db,
            user_id=user_id,
            session_id=session_id,
            run_id=run_id,
            amount=0.0,
            source_domain=SourceDomain.AGENT_TOOL,
            billing_kind=BillingKind.TOOL_USAGE,
            tool_name=tool_name,
            cost_usd=0.0,
            app_kind=app_kind,
            usage_metadata={
                "tool_name": tool_name,
                "succeeded": succeeded,
            },
        )

    async def _settle_tool_direct(
        self,
        db: AsyncSession,
        *,
        reservation_id: str,
        actual_cost_usd: float,
        provider: str | None,
        latency_ms: int | None,
        extra_usage_metadata: dict[str, Any] | None,
    ) -> BillingSettlementResult:
        actual_usd = Decimal(str(max(actual_cost_usd, 0.0)))
        actual_credits = usd_to_credits(actual_usd)
        usage_payload = {
            "provider": provider,
            "latency_ms": latency_ms,
            "cost_usd": float(actual_usd),
        }
        if extra_usage_metadata:
            usage_payload.update(extra_usage_metadata)
        return await self._reservation_service.settle(
            db,
            reservation_id=reservation_id,
            actual_credits=actual_credits,
            actual_usd=actual_usd,
            usage_payload=usage_payload,
        )

    async def release_tool_call_by_reservation_id(
        self,
        db: AsyncSession,
        *,
        reservation_id: str,
        reason: str,
    ) -> BillingSettlementResult:
        """Release one tool reservation by its persisted reservation id."""
        return await self._reservation_service.release(
            db,
            reservation_id=reservation_id,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Quote helpers
    # ------------------------------------------------------------------

    # Reserve for 25 % of input tokens as cache writes.  Only the first
    # request in a conversation writes the full prompt to the cache; later
    # turns are almost entirely cache reads.  25 % is conservative enough
    # to cover the occasional cache miss while avoiding the 2× over-
    # reservation that 100 % caused for users near their credit limit.
    # Tune up if shortfalls from cache writes become common.
    _CACHE_WRITE_RESERVE_FRACTION = Decimal("0.25")
    # Keep individual LLM holds readable in the UI and avoid pinning an
    # outsized share of the user's balance before settlement.
    _MAX_LLM_RESERVE_CREDITS = Decimal("15")

    async def _quote_llm_call(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        model_id: str,
        pricing: ModelPricing,
        input_tokens: int,
        model_cap: int,
    ) -> tuple[BillingQuote, int]:
        """Estimate a bounded LLM reservation and affordable output cap."""
        input_cost_usd = Decimal(str((input_tokens / 1_000_000) * pricing.input_price_per_million))
        cache_write_tokens_est = (
            int(input_tokens * float(self._CACHE_WRITE_RESERVE_FRACTION))
            if pricing.cache_write_price_per_million > 0
            else 0
        )
        cache_write_cost_usd = Decimal(
            str((cache_write_tokens_est / 1_000_000) * pricing.cache_write_price_per_million)
        )
        balance = await self._credit_service.get_balance(db, user_id)
        available_credits = balance.credits + balance.bonus_credits if balance is not None else 0.0
        available_usd = credits_to_usd(available_credits)
        safety_margin_usd = Decimal("0.001")
        if pricing.output_price_per_million <= 0:
            affordable_cap = model_cap
        else:
            available_for_output = max(
                Decimal("0"),
                available_usd - input_cost_usd - cache_write_cost_usd - safety_margin_usd,
            )
            affordable_cap = math.floor(
                float(available_for_output) / (pricing.output_price_per_million / 1_000_000)
            )
        output_cap = max(0, min(model_cap, affordable_cap))
        if output_cap < _MIN_USEFUL_OUTPUT_TOKENS:
            raise InsufficientCreditsError(
                "Insufficient credits for a useful response",
                phase="reserve",
                available_credits=float(available_credits),
                required_credits=float(
                    usd_to_credits(
                        float(input_cost_usd)
                        + float(cache_write_cost_usd)
                        + (_MIN_USEFUL_OUTPUT_TOKENS / 1_000_000) * pricing.output_price_per_million
                    )
                ),
            )

        output_cost_usd = Decimal(str((output_cap / 1_000_000) * pricing.output_price_per_million))
        uncapped_reserve_usd = (
            input_cost_usd + cache_write_cost_usd + output_cost_usd + safety_margin_usd
        )
        reserve_usd = min(
            uncapped_reserve_usd,
            credits_to_usd(self._MAX_LLM_RESERVE_CREDITS),
        )
        return (
            BillingQuote(
                strategy="bounded",
                reserve_usd=reserve_usd,
                max_usd=uncapped_reserve_usd,
                metadata={
                    "input_tokens_estimate": input_tokens,
                    "cache_write_tokens_estimate": cache_write_tokens_est,
                    "output_token_cap": output_cap,
                },
            ),
            output_cap,
        )

    @staticmethod
    def estimate_tokens(messages: list[Any]) -> int:
        """Estimate input tokens from the final message payload."""
        serialized = json.dumps(
            [LLMBillingService._serialize_for_token_estimation(msg) for msg in messages],
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )
        if not serialized:
            return 0
        if _ENCODING is None:
            return max(1, len(serialized) // 4)
        return len(_ENCODING.encode(serialized))

    @staticmethod
    def _serialize_for_token_estimation(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json", exclude_none=True)
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if isinstance(value, dict):
            return value
        if isinstance(value, (list, tuple)):
            return [LLMBillingService._serialize_for_token_estimation(v) for v in value]
        return str(value)

    @staticmethod
    def build_chat_provider_options(
        *,
        llm_config: LLMConfig,
        output_token_cap: int,
    ) -> dict[str, Any] | None:
        """Build provider options that enforce the same cap used for reservation."""
        api_type = llm_config.api_type.value
        if api_type == "openai":
            return {"openai": {"max_output_tokens": output_token_cap}}
        if api_type == "anthropic":
            return {"anthropic": {"max_tokens": output_token_cap}}
        if api_type == "gemini":
            return {"gemini": {"max_output_tokens": output_token_cap}}
        return {"custom": {"max_tokens": output_token_cap}}

    @staticmethod
    def _chat_model_output_cap(*, llm_config: LLMConfig) -> int:
        api_type = llm_config.api_type.value
        if api_type == "openai":
            return 64_000
        if api_type == "anthropic":
            return 16_384
        if api_type == "gemini":
            return max(256, llm_config.max_message_chars // 4)
        return 16_384

    @staticmethod
    def _agent_model_output_cap(model: Model) -> int:
        for attr in ("max_output_tokens", "max_tokens", "max_completion_tokens"):
            value = getattr(model, attr, None)
            if isinstance(value, int) and value > 0:
                return value
        return 8_192

    @staticmethod
    def _provider_from_api_type(api_type: APITypes):
        from ii_agent.agent.types import Provider

        value = getattr(api_type, "value", api_type)
        mapping = {
            "openai": Provider.OPENAI,
            "anthropic": Provider.ANTHROPIC,
            "gemini": Provider.GOOGLE,
        }
        return mapping.get(str(value), None)

    # ------------------------------------------------------------------
    # Internal math
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate(record: TokenRecord, pricing: ModelPricing) -> Decimal:
        """Pure math — USD cost converted to credits (Decimal)."""
        return usd_to_credits(LLMBillingService._calculate_usd(record, pricing))

    @staticmethod
    def _calculate_usd(record: TokenRecord, pricing: ModelPricing) -> Decimal:
        """Return direct USD cost for a token record.

        All arithmetic is done in Decimal to avoid float precision loss
        that compounds across high-volume billing.  Provider prices and
        ``direct_cost`` arrive as floats and are converted once at the
        boundary via ``Decimal(str(...))``.
        """
        _M = Decimal("1000000")
        input_cost = (
            Decimal(record.input_tokens) * Decimal(str(pricing.input_price_per_million)) / _M
        )
        output_cost = (
            Decimal(record.output_tokens) * Decimal(str(pricing.output_price_per_million)) / _M
        )
        cache_write_cost = (
            Decimal(record.cache_write_tokens)
            * Decimal(str(pricing.cache_write_price_per_million))
            / _M
        )
        cache_read_cost = (
            Decimal(record.cache_read_tokens)
            * Decimal(str(pricing.cache_read_price_per_million))
            / _M
        )

        return (
            input_cost
            + output_cost
            + cache_write_cost
            + cache_read_cost
            + Decimal(str(record.direct_cost))
        )
