"""Comprehensive unit tests for billing/service.py - BillingService webhook handling."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import stripe

from ii_agent.billing.exceptions import BillingConfigurationError, BillingServiceError
from ii_agent.billing.service import BillingService


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_service(settings_factory, *, webhook_secret="whsec_test"):
    settings = settings_factory(stripe={"webhook_secret": webhook_secret})
    return BillingService(settings=settings)


def _make_event(event_type: str, obj: dict) -> MagicMock:
    event = MagicMock(spec=stripe.Event)
    event.get = lambda key, default=None: {
        "type": event_type,
        "id": "evt_test_123",
        "data": {"object": obj},
    }.get(key, default)
    return event


# ---------------------------------------------------------------------------
# construct_webhook_event
# ---------------------------------------------------------------------------


class TestConstructWebhookEvent:
    def test_raises_when_webhook_secret_not_configured(self, settings_factory):
        service = _make_service(settings_factory, webhook_secret=None)
        with pytest.raises(BillingConfigurationError, match="webhook secret"):
            service.construct_webhook_event(b"{}", "sig")

    def test_raises_when_signature_is_none(self, settings_factory):
        service = _make_service(settings_factory)
        with pytest.raises(BillingServiceError, match="Missing Stripe signature"):
            service.construct_webhook_event(b"{}", None)

    def test_raises_on_invalid_payload(self, settings_factory, monkeypatch):
        service = _make_service(settings_factory)
        monkeypatch.setattr(
            stripe.Webhook,
            "construct_event",
            lambda *a, **kw: (_ for _ in ()).throw(ValueError("bad")),
        )
        with pytest.raises(BillingServiceError, match="Invalid Stripe webhook payload"):
            service.construct_webhook_event(b"bad", "sig")

    def test_raises_on_signature_verification_error(self, settings_factory, monkeypatch):
        service = _make_service(settings_factory)

        def _raise(*args, **kwargs):
            raise stripe.error.SignatureVerificationError("bad sig", "sig")

        monkeypatch.setattr(stripe.Webhook, "construct_event", _raise)
        with pytest.raises(BillingServiceError, match="Invalid Stripe signature"):
            service.construct_webhook_event(b"{}", "sig_bad")

    def test_succeeds_with_valid_event(self, settings_factory, monkeypatch):
        service = _make_service(settings_factory)
        mock_event = MagicMock(spec=stripe.Event)
        monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **kw: mock_event)
        result = service.construct_webhook_event(b"payload", "sig_valid")
        assert result is mock_event


# ---------------------------------------------------------------------------
# handle_webhook_event - dispatch
# ---------------------------------------------------------------------------


class TestHandleWebhookEventDispatch:
    @pytest.mark.asyncio
    async def test_unhandled_event_is_ignored(self, settings_factory):
        service = _make_service(settings_factory)
        event = _make_event("payment_intent.created", {})
        # Should not raise
        await service.handle_webhook_event(event=event)

    @pytest.mark.asyncio
    async def test_checkout_session_completed_dispatched(self, settings_factory):
        service = _make_service(settings_factory)
        called = []

        async def _fake_handler(event_id, obj):
            called.append(event_id)

        service._handle_checkout_completed = _fake_handler
        event = _make_event("checkout.session.completed", {})
        await service.handle_webhook_event(event=event)
        assert len(called) == 1

    @pytest.mark.asyncio
    async def test_invoice_payment_succeeded_dispatched(self, settings_factory):
        service = _make_service(settings_factory)
        called = []

        async def _fake_handler(event_id, obj):
            called.append(event_id)

        service._handle_invoice_paid = _fake_handler
        event = _make_event("invoice.payment_succeeded", {})
        await service.handle_webhook_event(event=event)
        assert len(called) == 1

    @pytest.mark.asyncio
    async def test_subscription_deleted_dispatched(self, settings_factory):
        service = _make_service(settings_factory)
        called = []

        async def _fake_handler(event_id, obj):
            called.append(event_id)

        service._handle_subscription_deleted = _fake_handler
        event = _make_event("customer.subscription.deleted", {})
        await service.handle_webhook_event(event=event)
        assert len(called) == 1

    @pytest.mark.asyncio
    async def test_subscription_updated_dispatched(self, settings_factory):
        service = _make_service(settings_factory)
        called = []

        async def _fake_handler(event_id, obj):
            called.append(event_id)

        service._handle_subscription_updated = _fake_handler
        event = _make_event("customer.subscription.updated", {})
        await service.handle_webhook_event(event=event)
        assert len(called) == 1


# ---------------------------------------------------------------------------
# _plan_cycle_from_price
# ---------------------------------------------------------------------------


class TestPlanCycleFromPrice:
    def test_returns_plan_and_cycle_for_known_price(self, settings_factory):
        service = _make_service(settings_factory)
        result = service._plan_cycle_from_price("price_pro_m")
        assert result == ("pro", "monthly")

    def test_returns_none_for_unknown_price(self, settings_factory):
        service = _make_service(settings_factory)
        assert service._plan_cycle_from_price("price_unknown") is None

    def test_returns_none_for_none_price(self, settings_factory):
        service = _make_service(settings_factory)
        assert service._plan_cycle_from_price(None) is None

    def test_returns_plus_annually(self, settings_factory):
        service = _make_service(settings_factory)
        result = service._plan_cycle_from_price("price_plus_a")
        assert result == ("plus", "annually")


# ---------------------------------------------------------------------------
# _normalize_billing_cycle
# ---------------------------------------------------------------------------


class TestNormalizeBillingCycle:
    def test_month_maps_to_monthly(self):
        assert BillingService._normalize_billing_cycle("month") == "monthly"

    def test_year_maps_to_annually(self):
        assert BillingService._normalize_billing_cycle("year") == "annually"

    def test_monthly_maps_to_monthly(self):
        assert BillingService._normalize_billing_cycle("monthly") == "monthly"

    def test_none_returns_none(self):
        assert BillingService._normalize_billing_cycle(None) is None

    def test_unknown_returns_none(self):
        assert BillingService._normalize_billing_cycle("weekly") is None


# ---------------------------------------------------------------------------
# _plan_credits
# ---------------------------------------------------------------------------


class TestPlanCredits:
    def test_returns_credits_for_pro(self, settings_factory):
        service = _make_service(settings_factory)
        assert service._plan_credits("pro") == 250.0

    def test_returns_credits_for_plus(self, settings_factory):
        service = _make_service(settings_factory)
        assert service._plan_credits("plus") == 100.0

    def test_returns_credits_for_free(self, settings_factory):
        service = _make_service(settings_factory)
        assert service._plan_credits("free") == 10.0

    def test_returns_none_for_unknown(self, settings_factory):
        service = _make_service(settings_factory)
        assert service._plan_credits("enterprise") is None

    def test_returns_none_for_none(self, settings_factory):
        service = _make_service(settings_factory)
        assert service._plan_credits(None) is None


# ---------------------------------------------------------------------------
# _to_datetime
# ---------------------------------------------------------------------------


class TestToDatetime:
    def test_converts_timestamp(self):
        result = BillingService._to_datetime(1999999999)
        assert result is not None
        assert result.year == 2033

    def test_returns_none_for_zero(self):
        assert BillingService._to_datetime(0) is None

    def test_returns_none_for_none(self):
        assert BillingService._to_datetime(None) is None


# ---------------------------------------------------------------------------
# _as_dict
# ---------------------------------------------------------------------------


class TestAsDict:
    def test_returns_empty_dict_for_none(self):
        assert BillingService._as_dict(None) == {}

    def test_returns_dict_unchanged(self):
        d = {"key": "value"}
        assert BillingService._as_dict(d) is d

    def test_converts_stripe_object_with_to_dict_recursive(self):
        obj = MagicMock()
        obj.to_dict_recursive.return_value = {"id": "sub_1"}
        assert BillingService._as_dict(obj) == {"id": "sub_1"}


# ---------------------------------------------------------------------------
# _ensure_api_key
# ---------------------------------------------------------------------------


class TestEnsureApiKey:
    def test_raises_when_secret_key_is_none(self, settings_factory):
        service = _make_service(settings_factory)
        service._stripe = MagicMock()
        service._stripe.secret_key = None
        from ii_agent.billing.exceptions import StripeConfigError

        with pytest.raises(StripeConfigError):
            service._ensure_api_key()

    def test_sets_stripe_api_key(self, settings_factory):
        service = _make_service(settings_factory)
        service._ensure_api_key()
        assert stripe.api_key == "sk_test_123"


# ---------------------------------------------------------------------------
# _get_price_id
# ---------------------------------------------------------------------------


class TestGetPriceId:
    def test_returns_price_id_for_valid_plan_and_cycle(self, settings_factory):
        service = _make_service(settings_factory)
        assert service._get_price_id("pro", "monthly") == "price_pro_m"

    def test_raises_for_unsupported_plan(self, settings_factory):
        from ii_agent.billing.exceptions import BillingUnsupportedPlanError

        service = _make_service(settings_factory)
        with pytest.raises(BillingUnsupportedPlanError):
            service._get_price_id("enterprise", "monthly")

    def test_raises_for_missing_price_configuration(self, settings_factory):
        settings = settings_factory(stripe={"price_pro_monthly": None})
        service = BillingService(settings=settings)
        with pytest.raises(BillingConfigurationError):
            service._get_price_id("pro", "monthly")
