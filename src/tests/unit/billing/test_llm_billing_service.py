"""Unit tests for LLMBillingService — token cost calculation and credit deduction."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from ii_agent.billing.credits.pricing import ModelPricing
from ii_agent.billing.credits.utils import usd_to_credits
from ii_agent.billing.reservations.types import BillingQuote
from ii_agent.core.llm.billing_service import LLMBillingService
from ii_agent.core.llm.token_record import TokenRecord

pytestmark = pytest.mark.unit

_USER_ID = str(uuid.uuid4())
_SESSION_ID = str(uuid.uuid4())


def _make_config() -> MagicMock:
    return MagicMock()


def _make_usage_service(*, deduct_result: bool = True) -> MagicMock:
    svc = MagicMock()
    svc.deduct_and_track_session_usage = AsyncMock(return_value=deduct_result)
    return svc


def _make_billing_service(
    usage_service: MagicMock | None = None,
    credit_service: MagicMock | None = None,
    reservation_service: MagicMock | None = None,
    outbox_service: MagicMock | None = None,
) -> tuple[LLMBillingService, MagicMock]:
    usage_svc = usage_service or _make_usage_service()
    billing_svc = LLMBillingService(
        usage_service=usage_svc,
        credit_service=credit_service or MagicMock(),
        reservation_service=reservation_service or MagicMock(),
        config=_make_config(),
        outbox_service=outbox_service,
    )
    return billing_svc, usage_svc


# ---------------------------------------------------------------------------
# _calculate — pure math
# ---------------------------------------------------------------------------


class TestCalculate:
    """Tests for the static _calculate method."""

    def test_input_and_output_tokens_only(self):
        """Basic cost with only input/output tokens."""
        record = TokenRecord(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model_id="claude-sonnet-4-5",
        )
        pricing = ModelPricing.get_default_pricing("claude-sonnet-4-5")
        credits = LLMBillingService._calculate(record, pricing)

        # input: 1M * 3.0/1M = $3.0, output: 1M * 15.0/1M = $15.0
        expected_usd = 3.0 + 15.0
        assert abs(credits - usd_to_credits(expected_usd)) < 0.001

    def test_cache_tokens_included(self):
        """Cache read/write tokens contribute to cost."""
        record = TokenRecord(
            input_tokens=500_000,
            output_tokens=200_000,
            cache_read_tokens=300_000,
            cache_write_tokens=100_000,
            model_id="claude-sonnet-4-5",
        )
        pricing = ModelPricing.get_default_pricing("claude-sonnet-4-5")
        credits = LLMBillingService._calculate(record, pricing)

        expected_usd = (
            (500_000 / 1_000_000) * 3.0       # input
            + (200_000 / 1_000_000) * 15.0     # output
            + (100_000 / 1_000_000) * 3.75     # cache write
            + (300_000 / 1_000_000) * 0.3      # cache read
        )
        assert abs(credits - usd_to_credits(expected_usd)) < 0.001

    def test_direct_cost_added(self):
        """direct_cost on the TokenRecord is added to total USD."""
        record = TokenRecord(
            input_tokens=0,
            output_tokens=0,
            model_id="claude-sonnet-4-5",
            direct_cost=1.0,
        )
        pricing = ModelPricing.get_default_pricing("claude-sonnet-4-5")
        credits = LLMBillingService._calculate(record, pricing)

        assert abs(credits - usd_to_credits(1.0)) < 0.001

    def test_zero_tokens_zero_credits(self):
        """Zero tokens and zero direct_cost yields zero credits."""
        record = TokenRecord(model_id="claude-sonnet-4-5")
        pricing = ModelPricing.get_default_pricing("claude-sonnet-4-5")
        credits = LLMBillingService._calculate(record, pricing)

        assert credits == 0.0

    def test_different_models_different_costs(self):
        """Same token counts yield different costs for different models."""
        record = TokenRecord(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model_id="gpt-4o",
        )
        gpt4o_pricing = ModelPricing.get_default_pricing("gpt-4o")
        opus_pricing = ModelPricing.get_default_pricing("claude-opus-4")

        gpt4o_credits = LLMBillingService._calculate(record, gpt4o_pricing)
        opus_credits = LLMBillingService._calculate(
            TokenRecord(
                input_tokens=1_000_000,
                output_tokens=1_000_000,
                model_id="claude-opus-4",
            ),
            opus_pricing,
        )

        # claude-opus-4 is much more expensive
        assert opus_credits > gpt4o_credits

    def test_small_token_count_precision(self):
        """Small token counts don't get lost to floating-point."""
        record = TokenRecord(
            input_tokens=1,
            output_tokens=1,
            model_id="claude-sonnet-4-5",
        )
        pricing = ModelPricing.get_default_pricing("claude-sonnet-4-5")
        credits = LLMBillingService._calculate(record, pricing)

        expected_usd = (1 / 1_000_000) * 3.0 + (1 / 1_000_000) * 15.0
        assert credits > 0
        assert abs(credits - usd_to_credits(expected_usd)) < 1e-9


class TestQuoteLLMCall:
    """Tests for the _quote_llm_call minimum-useful-output guard."""

    @pytest.mark.asyncio
    async def test_raises_insufficient_credits_when_output_cap_below_minimum(self):
        """Users with too few credits for 128 output tokens get a clear error."""
        from ii_agent.billing.exceptions import InsufficientCreditsError
        from ii_agent.billing.credits.schemas import CreditBalance
        from datetime import datetime, timezone

        credit_svc = MagicMock()
        # Give user barely enough for input but not 128 output tokens
        credit_svc.get_balance = AsyncMock(
            return_value=CreditBalance(
                user_id=_USER_ID,
                credits=0.01,  # ~$0.00015 — can't afford meaningful output
                bonus_credits=0.0,
                updated_at=datetime.now(timezone.utc),
            )
        )
        billing_svc, _ = _make_billing_service(credit_service=credit_svc)
        pricing = ModelPricing.get_default_pricing("claude-sonnet-4-5")

        with pytest.raises(InsufficientCreditsError, match="useful response"):
            await billing_svc._quote_llm_call(
                AsyncMock(),
                user_id=_USER_ID,
                model_id="claude-sonnet-4-5",
                pricing=pricing,
                input_tokens=100,
                model_cap=8192,
            )

    @pytest.mark.asyncio
    async def test_succeeds_with_sufficient_credits(self):
        """Users with enough credits get a valid quote and output cap."""
        from ii_agent.billing.credits.schemas import CreditBalance
        from datetime import datetime, timezone

        credit_svc = MagicMock()
        credit_svc.get_balance = AsyncMock(
            return_value=CreditBalance(
                user_id=_USER_ID,
                credits=100.0,  # plenty
                bonus_credits=0.0,
                updated_at=datetime.now(timezone.utc),
            )
        )
        billing_svc, _ = _make_billing_service(credit_service=credit_svc)
        pricing = ModelPricing.get_default_pricing("claude-sonnet-4-5")

        quote, output_cap = await billing_svc._quote_llm_call(
            AsyncMock(),
            user_id=_USER_ID,
            model_id="claude-sonnet-4-5",
            pricing=pricing,
            input_tokens=1000,
            model_cap=8192,
        )

        assert output_cap >= 128
        assert quote.strategy == "bounded"
        assert quote.reserve_usd > 0

    @pytest.mark.asyncio
    async def test_quote_includes_cache_write_cost(self):
        """Anthropic quotes should reserve for estimated cache writes (25 % of input)."""
        from ii_agent.billing.credits.schemas import CreditBalance
        from datetime import datetime, timezone

        credit_svc = MagicMock()
        credit_svc.get_balance = AsyncMock(
            return_value=CreditBalance(
                user_id=_USER_ID,
                credits=100.0,
                bonus_credits=0.0,
                updated_at=datetime.now(timezone.utc),
            )
        )
        billing_svc, _ = _make_billing_service(credit_service=credit_svc)
        pricing = ModelPricing.get_default_pricing("claude-sonnet-4-5")

        quote, output_cap = await billing_svc._quote_llm_call(
            AsyncMock(),
            user_id=_USER_ID,
            model_id="claude-sonnet-4-5",
            pricing=pricing,
            input_tokens=1000,
            model_cap=1000,
        )

        cache_write_est = int(1000 * 0.25)  # 25 % of input tokens
        expected_reserve_usd = (
            (1000 / 1_000_000) * pricing.input_price_per_million
            + (1000 / 1_000_000) * pricing.output_price_per_million
            + (cache_write_est / 1_000_000) * pricing.cache_write_price_per_million
            + 0.001
        )
        assert output_cap == 1000
        assert float(quote.reserve_usd) == pytest.approx(expected_reserve_usd)
        assert quote.metadata["cache_write_tokens_estimate"] == cache_write_est


class TestReserveToolCall:
    @pytest.mark.asyncio
    async def test_rejects_post_facto_quotes(self):
        billing_svc, _ = _make_billing_service()

        with pytest.raises(ValueError, match="exact or bounded upfront quote"):
            await billing_svc.reserve_tool_call(
                AsyncMock(),
                user_id=_USER_ID,
                session_id=_SESSION_ID,
                run_id=None,
                source_domain="chat_tool",
                source_id="tool-call-1",
                tool_name="generate_image",
                quote=BillingQuote(strategy="post_facto", reserve_usd=0, max_usd=0),
                idempotency_key="tool-idem",
                app_kind="chat",
            )


class TestToolReservationByIdHelpers:
    @pytest.mark.asyncio
    async def test_settle_tool_call_by_reservation_id_forwards_settlement_payload(self):
        reservation_service = MagicMock()
        reservation_service.settle = AsyncMock(return_value="settled")
        billing_svc, _ = _make_billing_service(reservation_service=reservation_service)

        result = await billing_svc.settle_tool_call_by_reservation_id(
            AsyncMock(),
            reservation_id="res-1",
            actual_cost_usd=0.25,
            provider="openai",
            latency_ms=42,
            extra_usage_metadata={"tool_name": "generate_storybook", "run_id": "run-1"},
        )

        assert result == "settled"
        kwargs = reservation_service.settle.await_args.kwargs
        assert kwargs["reservation_id"] == "res-1"
        assert float(kwargs["actual_usd"]) == 0.25
        assert float(kwargs["actual_credits"]) == pytest.approx(float(usd_to_credits(0.25)))
        assert kwargs["usage_payload"]["tool_name"] == "generate_storybook"
        assert kwargs["usage_payload"]["run_id"] == "run-1"

    @pytest.mark.asyncio
    async def test_release_tool_call_by_reservation_id_forwards_reason(self):
        reservation_service = MagicMock()
        reservation_service.release = AsyncMock(return_value="released")
        billing_svc, _ = _make_billing_service(reservation_service=reservation_service)

        result = await billing_svc.release_tool_call_by_reservation_id(
            AsyncMock(),
            reservation_id="res-1",
            reason="storybook_failed",
        )

        assert result == "released"
        reservation_service.release.assert_awaited_once_with(
            ANY,
            reservation_id="res-1",
            reason="storybook_failed",
        )


class TestUsageFactOutboxDelegation:
    @pytest.mark.asyncio
    async def test_settle_chat_llm_call_uses_outbox_when_configured(self):
        from ii_agent.core.llm.billing_service import ReservedLLMCall
        from ii_agent.billing.reservations.types import ReservationHold

        outbox_service = MagicMock()
        outbox_service.capture_llm_fact = AsyncMock(return_value=SimpleNamespace(id=7))
        outbox_service.process_fact = AsyncMock(return_value="processed")
        billing_svc, _ = _make_billing_service(outbox_service=outbox_service)
        pricing = ModelPricing.get_default_pricing("claude-sonnet-4-5")

        reservation = ReservedLLMCall(
            hold=ReservationHold(
                reservation_id="res-1",
                idempotency_key="idem-1",
                reserved_credits=Decimal("1"),
                reserved_bonus_credits=Decimal("0"),
                quoted_usd=Decimal("0.1"),
                max_usd=Decimal("0.1"),
            ),
            input_tokens_estimate=100,
            output_token_cap=256,
            pricing=pricing,
        )
        result = await billing_svc.settle_chat_llm_call(
            AsyncMock(),
            reservation=reservation,
            user_id=_USER_ID,
            session_id=_SESSION_ID,
            run_id="run-1",
            token_record=TokenRecord(
                input_tokens=10,
                output_tokens=5,
                model_id="claude-sonnet-4-5",
            ),
            provider="anthropic",
            request_kind="chat_response",
            latency_ms=42,
        )

        assert result == "processed"
        outbox_service.capture_llm_fact.assert_awaited_once()
        outbox_service.process_fact.assert_awaited_once_with(ANY, fact_id=7)

    @pytest.mark.asyncio
    async def test_settle_tool_call_by_reservation_id_uses_outbox_when_configured(self):
        outbox_service = MagicMock()
        outbox_service.capture_tool_fact = AsyncMock(return_value=SimpleNamespace(id=9))
        outbox_service.process_fact = AsyncMock(return_value="processed")
        billing_svc, _ = _make_billing_service(outbox_service=outbox_service)

        result = await billing_svc.settle_tool_call_by_reservation_id(
            AsyncMock(),
            reservation_id="res-1",
            actual_cost_usd=0.25,
            provider="openai",
            latency_ms=15,
            extra_usage_metadata={"app_kind": "chat", "tool_name": "generate_image"},
        )

        assert result == "processed"
        outbox_service.capture_tool_fact.assert_awaited_once()
        outbox_service.process_fact.assert_awaited_once_with(ANY, fact_id=9)
