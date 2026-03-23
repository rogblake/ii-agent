"""Unit tests for LLMBillingService — token cost calculation and credit deduction."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid
from decimal import Decimal
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from ii_agent.billing.credits.schemas import CreditBalance
from ii_agent.billing.types import BillingScope, SubjectKind
from ii_agent.billing.exceptions import BillingDuplicateOperationError
from ii_agent.billing.credits.pricing import ModelPricing
from ii_agent.billing.credits.utils import usd_to_credits
from ii_agent.billing.reservations.types import BillingQuote, ReservationHold, ReservationStatus
from ii_agent.core.llm.billing_service import LLMBillingService
from ii_agent.core.llm.token_record import TokenRecord
from ii_agent.core.config.llm_config import APITypes, LLMConfig

pytestmark = pytest.mark.unit

_USER_ID = str(uuid.uuid4())
_SESSION_ID = str(uuid.uuid4())


class _NullAsyncContext:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeDB:
    def begin_nested(self):
        return _NullAsyncContext()


def _make_config() -> MagicMock:
    return MagicMock()


def _make_usage_service(*, deduct_result: bool = True) -> MagicMock:
    svc = MagicMock()
    svc.record_settled_usage = AsyncMock(return_value=1)
    return svc


def _make_billing_service(
    usage_service: MagicMock | None = None,
    credit_service: MagicMock | None = None,
    reservation_service: MagicMock | None = None,
) -> tuple[LLMBillingService, MagicMock]:
    usage_svc = usage_service or _make_usage_service()
    reservation_service_mock = reservation_service or MagicMock()
    if not isinstance(getattr(reservation_service_mock, "reserve", None), AsyncMock):
        reservation_service_mock.reserve = AsyncMock()
    if not isinstance(
        getattr(reservation_service_mock, "get_hold_by_idempotency_key", None),
        AsyncMock,
    ):
        reservation_service_mock.get_hold_by_idempotency_key = AsyncMock(return_value=None)
    if not isinstance(
        getattr(reservation_service_mock, "capture_settlement_input", None), AsyncMock
    ):
        reservation_service_mock.capture_settlement_input = AsyncMock()
    if not isinstance(getattr(reservation_service_mock, "settle", None), AsyncMock):
        reservation_service_mock.settle = AsyncMock(return_value="settled")
    if not isinstance(getattr(reservation_service_mock, "release", None), AsyncMock):
        reservation_service_mock.release = AsyncMock(return_value="released")
    if not isinstance(getattr(reservation_service_mock, "mark_settlement_failed", None), AsyncMock):
        reservation_service_mock.mark_settlement_failed = AsyncMock()
    if not isinstance(
        getattr(reservation_service_mock, "retry_settlement_from_capture", None),
        AsyncMock,
    ):
        reservation_service_mock.retry_settlement_from_capture = AsyncMock(return_value="retried")
    billing_svc = LLMBillingService(
        usage_service=usage_svc,
        credit_service=credit_service or MagicMock(),
        reservation_service=reservation_service_mock,
        config=_make_config(),
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
            (500_000 / 1_000_000) * 3.0  # input
            + (200_000 / 1_000_000) * 15.0  # output
            + (100_000 / 1_000_000) * 3.75  # cache write
            + (300_000 / 1_000_000) * 0.3  # cache read
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
        """Users with zero credits still get a clear insufficient-balance error."""
        from ii_agent.billing.exceptions import InsufficientCreditsError
        from ii_agent.billing.credits.schemas import CreditBalance
        from datetime import datetime, timezone

        credit_svc = MagicMock()
        # Controlled shortfall requires a positive starting balance.
        credit_svc.get_balance = AsyncMock(
            return_value=CreditBalance(
                user_id=_USER_ID,
                credits=0.0,
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
    async def test_positive_balance_can_get_useful_output_with_controlled_shortfall_budget(self):
        """A small positive balance can still quote a useful response via the debt window."""
        from ii_agent.billing.credits.schemas import CreditBalance
        from datetime import datetime, timezone

        credit_svc = MagicMock()
        credit_svc.get_balance = AsyncMock(
            return_value=CreditBalance(
                user_id=_USER_ID,
                credits=0.01,
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
            input_tokens=100,
            model_cap=8192,
        )

        assert output_cap >= 128
        assert quote.metadata["controlled_shortfall_budget_credits"] == 50.0

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

    @pytest.mark.asyncio
    async def test_quote_caps_reservation_hold_at_fifteen_credits(self):
        """Large output caps should not reserve more than 15 credits upfront."""
        from ii_agent.billing.credits.schemas import CreditBalance
        from datetime import datetime, timezone

        credit_svc = MagicMock()
        credit_svc.get_balance = AsyncMock(
            return_value=CreditBalance(
                user_id=_USER_ID,
                credits=10_000.0,
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
            input_tokens=1_000,
            model_cap=20_000,
        )

        cache_write_est = int(1_000 * 0.25)
        expected_uncapped_usd = (
            (1_000 / 1_000_000) * pricing.input_price_per_million
            + (20_000 / 1_000_000) * pricing.output_price_per_million
            + (cache_write_est / 1_000_000) * pricing.cache_write_price_per_million
            + 0.001
        )

        assert output_cap == 20_000
        assert float(quote.reserve_usd) == pytest.approx(float(15 / usd_to_credits(1)))
        assert float(quote.max_usd) == pytest.approx(expected_uncapped_usd)
        assert quote.max_usd > quote.reserve_usd


class TestReserveToolCall:
    @pytest.mark.asyncio
    async def test_chat_llm_idempotency_key_uses_per_call_source_id(self):
        reservation_service = MagicMock()
        reservation_service.get_hold_by_idempotency_key = AsyncMock(return_value=None)

        async def _reserve(*_args, **kwargs):
            return ReservationHold(
                reservation_id="res-1",
                idempotency_key="chat-key",
                reserved_credits=Decimal("1"),
                reserved_bonus_credits=Decimal("0"),
                quoted_usd=Decimal("0.01"),
                max_usd=Decimal("0.02"),
                output_token_cap=kwargs["output_token_cap"],
            )

        reservation_service.reserve = AsyncMock(side_effect=_reserve)
        credit_svc = MagicMock()
        credit_svc.get_balance = AsyncMock(
            return_value=CreditBalance(
                user_id=_USER_ID,
                credits=100.0,
                bonus_credits=0.0,
                updated_at=datetime.now(timezone.utc),
            )
        )
        billing_svc, _ = _make_billing_service(
            credit_service=credit_svc,
            reservation_service=reservation_service,
        )
        llm_config = LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI, config_type="system")

        await billing_svc.reserve_chat_llm_call(
            _FakeDB(),
            scope=BillingScope.for_session(
                user_id=_USER_ID,
                app_kind="chat",
                session_id=_SESSION_ID,
                run_id="run-1",
            ),
            model_id="gpt-4o",
            llm_config=llm_config,
            messages=[{"role": "user", "content": "hello"}],
            source_id="run-1:step-2",
            request_kind="chat_turn",
        )

        reserve_kwargs = reservation_service.reserve.await_args.kwargs
        assert reserve_kwargs["idempotency_key"].endswith("run-1:step-2")
        assert not reserve_kwargs["idempotency_key"].endswith("chat_turn")

    @pytest.mark.asyncio
    async def test_chat_llm_quote_uses_current_available_balance(self):
        reservation_service = MagicMock()
        reservation_service.get_hold_by_idempotency_key = AsyncMock(return_value=None)

        async def _reserve(*_args, **kwargs):
            return ReservationHold(
                reservation_id="res-1",
                idempotency_key=kwargs["idempotency_key"],
                reserved_credits=Decimal("1"),
                reserved_bonus_credits=Decimal("0"),
                quoted_usd=Decimal("0.01"),
                max_usd=Decimal("0.02"),
                output_token_cap=kwargs["output_token_cap"],
            )

        reservation_service.reserve = AsyncMock(side_effect=_reserve)
        credit_svc = MagicMock()
        credit_svc.get_balance = AsyncMock(
            return_value=CreditBalance(
                user_id=_USER_ID,
                credits=100.0,
                bonus_credits=0.0,
                updated_at=datetime.now(timezone.utc),
            )
        )
        billing_svc, _ = _make_billing_service(
            credit_service=credit_svc,
            reservation_service=reservation_service,
        )
        llm_config = LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI, config_type="system")

        reservation = await billing_svc.reserve_chat_llm_call(
            _FakeDB(),
            scope=BillingScope.for_session(
                user_id=_USER_ID,
                app_kind="chat",
                session_id=_SESSION_ID,
            ),
            model_id="gpt-4o",
            llm_config=llm_config,
            messages=[{"role": "user", "content": "hello"}],
            source_id="usage-1",
            request_kind="usage-1",
        )

        assert reservation is not None
        credit_svc.get_balance.assert_awaited_once()
        assert reservation_service.get_hold_by_idempotency_key.await_count == 1

    @pytest.mark.asyncio
    async def test_chat_llm_allows_custom_source_domain(self):
        reservation_service = MagicMock()
        reservation_service.get_hold_by_idempotency_key = AsyncMock(return_value=None)

        async def _reserve(*_args, **kwargs):
            return ReservationHold(
                reservation_id="res-1",
                idempotency_key=kwargs["idempotency_key"],
                reserved_credits=Decimal("1"),
                reserved_bonus_credits=Decimal("0"),
                quoted_usd=Decimal("0.01"),
                max_usd=Decimal("0.02"),
                output_token_cap=kwargs["output_token_cap"],
            )

        reservation_service.reserve = AsyncMock(side_effect=_reserve)
        credit_svc = MagicMock()
        credit_svc.get_balance = AsyncMock(
            return_value=CreditBalance(
                user_id=_USER_ID,
                credits=100.0,
                bonus_credits=0.0,
                updated_at=datetime.now(timezone.utc),
            )
        )
        billing_svc, _ = _make_billing_service(
            credit_service=credit_svc,
            reservation_service=reservation_service,
        )
        llm_config = LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI, config_type="system")
        scope = BillingScope.for_subject(
            user_id=_USER_ID,
            app_kind="chat",
            subject_kind=SubjectKind.SESSION,
            subject_id=_SESSION_ID,
            billing_context="storybook",
            run_id="run-1",
        )

        reservation = await billing_svc.reserve_chat_llm_call(
            _FakeDB(),
            scope=scope,
            model_id="gpt-4o",
            llm_config=llm_config,
            messages=[{"role": "user", "content": "hello"}],
            source_id="node-1",
            request_kind="node-1",
            source_domain="storybook_llm",
        )

        assert reservation is not None
        reserve_kwargs = reservation_service.reserve.await_args.kwargs
        assert reserve_kwargs["source_domain"] == "storybook_llm"
        assert (
            reserve_kwargs["idempotency_key"]
            == f"storybook_llm:chat:storybook:session:{_SESSION_ID}:run-1:node-1"
        )

    @pytest.mark.asyncio
    async def test_rejects_post_facto_quotes(self):
        billing_svc, _ = _make_billing_service()

        with pytest.raises(ValueError, match="exact or bounded upfront quote"):
            await billing_svc.reserve_tool_call(
                AsyncMock(),
                scope=BillingScope.for_session(
                    user_id=_USER_ID,
                    app_kind="chat",
                    session_id=_SESSION_ID,
                ),
                source_domain="chat_tool",
                source_id="tool-call-1",
                tool_name="generate_image",
                quote=BillingQuote(strategy="post_facto", reserve_usd=0, max_usd=0),
            )

    @pytest.mark.asyncio
    async def test_tool_idempotency_key_uses_source_domain_namespace(self):
        reservation_service = MagicMock()
        reservation_service.reserve = AsyncMock(
            return_value=ReservationHold(
                reservation_id="tool-res-1",
                idempotency_key="voice_generation-key",
                reserved_credits=Decimal("1"),
                reserved_bonus_credits=Decimal("0"),
                quoted_usd=Decimal("0.01"),
                max_usd=Decimal("0.02"),
                status=ReservationStatus.RESERVED,
                was_created=True,
            )
        )
        billing_svc, _ = _make_billing_service(reservation_service=reservation_service)

        await billing_svc.reserve_tool_call(
            _FakeDB(),
            scope=BillingScope.for_session(
                user_id=_USER_ID,
                app_kind="chat",
                session_id=_SESSION_ID,
                billing_context="storybook",
                run_id="run-1",
            ),
            source_domain="voice_generation",
            source_id="page-1",
            tool_name="storybook_voiceover",
            quote=BillingQuote(
                strategy="bounded",
                reserve_usd=Decimal("0.01"),
                max_usd=Decimal("0.02"),
            ),
        )

        reserve_kwargs = reservation_service.reserve.await_args.kwargs
        assert reserve_kwargs["source_domain"] == "voice_generation"
        assert (
            reserve_kwargs["idempotency_key"]
            == f"voice_generation:chat:storybook:session:{_SESSION_ID}:run-1:page-1"
        )

    @pytest.mark.asyncio
    async def test_chat_llm_duplicate_operation_key_raises(self):
        reservation_service = MagicMock()
        reservation_service.get_hold_by_idempotency_key = AsyncMock(
            return_value=ReservationHold(
                reservation_id="res-dup",
                idempotency_key="chat-key",
                reserved_credits=Decimal("1"),
                reserved_bonus_credits=Decimal("0"),
                quoted_usd=Decimal("0.01"),
                max_usd=Decimal("0.02"),
                output_token_cap=1024,
                status=ReservationStatus.RESERVED,
                was_created=False,
            )
        )
        billing_svc, _ = _make_billing_service(
            credit_service=MagicMock(),
            reservation_service=reservation_service,
        )
        llm_config = LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI, config_type="system")

        with pytest.raises(BillingDuplicateOperationError, match="already in progress"):
            await billing_svc.reserve_chat_llm_call(
                _FakeDB(),
                scope=BillingScope.for_session(
                    user_id=_USER_ID,
                    app_kind="chat",
                    session_id=_SESSION_ID,
                ),
                model_id="gpt-4o",
                llm_config=llm_config,
                messages=[{"role": "user", "content": "hi"}],
                source_id="call-dup",
                request_kind="chat_response",
            )

    @pytest.mark.asyncio
    async def test_tool_duplicate_operation_key_raises(self):
        reservation_service = MagicMock()
        reservation_service.reserve = AsyncMock(
            return_value=ReservationHold(
                reservation_id="tool-res-dup",
                idempotency_key="tool-key",
                reserved_credits=Decimal("1"),
                reserved_bonus_credits=Decimal("0"),
                quoted_usd=Decimal("0.01"),
                max_usd=Decimal("0.02"),
                status=ReservationStatus.SETTLED,
                was_created=False,
            )
        )
        billing_svc, _ = _make_billing_service(
            credit_service=MagicMock(),
            reservation_service=reservation_service,
        )

        with pytest.raises(BillingDuplicateOperationError, match="already been finalized"):
            await billing_svc.reserve_tool_call(
                _FakeDB(),
                scope=BillingScope.for_session(
                    user_id=_USER_ID,
                    app_kind="chat",
                    session_id=_SESSION_ID,
                ),
                source_domain="chat_tool",
                source_id="tool-call-dup",
                tool_name="search_tool",
                quote=BillingQuote(
                    strategy="bounded",
                    reserve_usd=Decimal("0.01"),
                    max_usd=Decimal("0.02"),
                ),
            )


class TestToolReservationByIdHelpers:
    @pytest.mark.asyncio
    async def test_settle_tool_call_by_reservation_id_forwards_settlement_payload(self):
        reservation_service = MagicMock()
        reservation_service.capture_settlement_input = AsyncMock()
        reservation_service.settle = AsyncMock(return_value="settled")
        billing_svc, _ = _make_billing_service(reservation_service=reservation_service)
        db = AsyncMock()
        scope = BillingScope.for_session(
            user_id=_USER_ID,
            app_kind="chat",
            session_id=_SESSION_ID,
            run_id="run-1",
        )

        result = await billing_svc.settle_tool_call_by_reservation_id(
            db,
            scope=scope,
            reservation_id="res-1",
            actual_cost_usd=0.25,
            provider="openai",
            latency_ms=42,
            extra_usage_metadata={"tool_name": "generate_storybook", "run_id": "run-1"},
        )

        assert result == "settled"
        reservation_service.capture_settlement_input.assert_awaited_once()
        db.commit.assert_awaited_once()
        capture_kwargs = reservation_service.capture_settlement_input.await_args.kwargs
        assert capture_kwargs["reservation_id"] == "res-1"
        kwargs = reservation_service.settle.await_args.kwargs
        assert kwargs["reservation_id"] == "res-1"
        assert capture_kwargs["actual_usd"] == Decimal("0.25")
        assert capture_kwargs["actual_credits"] == usd_to_credits(Decimal("0.25"))
        assert capture_kwargs["usage_payload"] == {
            "app_kind": "chat",
            "subject_kind": "session",
            "subject_id": _SESSION_ID,
            "billing_context": "chatloop",
            "provider": "openai",
            "latency_ms": 42,
            "cost_usd": 0.25,
            "tool_name": "generate_storybook",
            "run_id": "run-1",
        }
        assert kwargs == capture_kwargs | {"reservation_id": "res-1"}

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


class TestManualRetrySettlement:
    @pytest.mark.asyncio
    async def test_manual_retry_delegates_to_reservation_service(self):
        reservation_service = MagicMock()
        reservation_service.retry_settlement_from_capture = AsyncMock(return_value="settled")
        billing_svc, _ = _make_billing_service(reservation_service=reservation_service)

        result = await billing_svc.manual_retry_settlement(
            AsyncMock(),
            reservation_id="res-1",
        )

        assert result == "settled"
        reservation_service.retry_settlement_from_capture.assert_awaited_once_with(
            ANY,
            reservation_id="res-1",
        )
