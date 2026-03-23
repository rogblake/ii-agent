"""Comprehensive unit tests for billing/webhook_handler.py - StripeWebhookHandler."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import stripe

from ii_agent.billing.reservations.types import ReservationStatus
from ii_agent.billing.exceptions import BillingConfigurationError, BillingServiceError
from ii_agent.billing.stripe_config import StripeConfig
from ii_agent.billing.webhook_handler import StripeWebhookHandler, SubscriptionContext


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _FakeBillingRepo:
    def __init__(self):
        self.events: dict = {}
        self.created: list = []
        self.claimed: list = []
        self.updated: list = []

    async def get_by_event_id(self, db, event_id):
        return self.events.get(event_id)

    async def claim_event(self, db, *, user_id, stripe_event_id):
        if stripe_event_id in self.events:
            return False  # Already claimed
        self.events[stripe_event_id] = {"user_id": user_id, "status": "processing"}
        self.claimed.append((user_id, stripe_event_id))
        return True

    async def update_by_event_id(self, db, *, stripe_event_id, **values):
        if stripe_event_id in self.events:
            self.events[stripe_event_id].update(values)
            self.updated.append((stripe_event_id, values))

    async def create(self, db, user_id, stripe_event_id, **values):
        record = {"user_id": user_id, **values}
        self.events[stripe_event_id] = record
        self.created.append((user_id, stripe_event_id, values))


class _FakeUserRepo:
    def __init__(self, users=None, customer_map=None):
        self.users = users or {}
        self.subscriptions: list = []
        self.customer_map: dict = customer_map or {}

    async def get_by_id(self, db, user_id):
        return self.users.get(user_id)

    async def lookup_by_customer_id(self, db, customer_id):
        return self.customer_map.get(customer_id)

    async def update_subscription(self, db, user, **kwargs):
        self.subscriptions.append({"user": user, **kwargs})


class _FakeBillingCustomerService:
    def __init__(self):
        self.customers = {}
        self.subscription_updates = []

    async def get_or_create(
        self, db, *, user_id, provider="stripe", external_customer_id, **kwargs
    ):
        key = (user_id, provider)
        if key not in self.customers:
            self.customers[key] = {
                "user_id": user_id,
                "provider": provider,
                "external_customer_id": external_customer_id,
            }
        return SimpleNamespace(**self.customers[key])

    async def update_subscription(self, db, user_id, *, provider="stripe", **kwargs):
        key = (user_id, provider)
        customer = self.customers.get(key)
        if customer is None:
            return None

        for field, value in kwargs.items():
            if value is not ...:
                customer[field] = value

        update = {"user_id": user_id, **kwargs}
        self.subscription_updates.append(update)
        return SimpleNamespace(**customer)

    async def lookup_user_id(self, db, external_customer_id, provider="stripe"):
        for key, val in self.customers.items():
            if val["external_customer_id"] == external_customer_id:
                return val["user_id"]
        return None


class _FakeReservationRepo:
    def __init__(self, *, held_regular=0, held_bonus=0, replayable_shortfalls=None):
        self.held_regular = held_regular
        self.held_bonus = held_bonus
        self.replayable_shortfalls = replayable_shortfalls or []

    async def get_outstanding_hold_totals(self, db, *, user_id):
        return self.held_regular, self.held_bonus

    async def list_replayable_shortfall_failures(self, db, *, user_id, limit=50):
        reservations = [
            reservation
            for reservation in self.replayable_shortfalls
            if getattr(reservation, "user_id", None) == user_id
            and getattr(reservation, "status", ReservationStatus.SETTLEMENT_FAILED)
            == ReservationStatus.SETTLEMENT_FAILED
            and getattr(reservation, "last_error", "settlement_shortfall_unreconciled")
            == "settlement_shortfall_unreconciled"
        ]
        return reservations[:limit]

    async def has_replayable_shortfall_failures(self, db, *, user_id):
        reservations = await self.list_replayable_shortfall_failures(db, user_id=user_id, limit=1)
        return bool(reservations)

    async def has_blocking_settlement_failures(self, db, *, user_id):
        return any(
            getattr(reservation, "user_id", None) == user_id
            and getattr(reservation, "status", None) == ReservationStatus.SETTLEMENT_FAILED
            for reservation in self.replayable_shortfalls
        )

    def set_status(self, reservation_id, status):
        for reservation in self.replayable_shortfalls:
            if getattr(reservation, "id", None) == reservation_id:
                reservation.status = status
                return


def _make_handler(
    settings_factory,
    *,
    user_repo=None,
    billing_repo=None,
    billing_customer_service=None,
    credit_service=None,
    reservation_repo=None,
    reservation_service=None,
    webhook_secret="whsec_test",
):
    settings = settings_factory(stripe={"webhook_secret": webhook_secret})
    return StripeWebhookHandler(
        stripe_config=StripeConfig(config=settings),
        billing_repo=billing_repo or _FakeBillingRepo(),
        user_repo=user_repo or _FakeUserRepo(),
        billing_customer_service=billing_customer_service or _FakeBillingCustomerService(),
        credit_service=credit_service,
        reservation_repo=reservation_repo,
        reservation_service=reservation_service,
    )


def _make_event(event_type: str, obj: dict) -> MagicMock:
    event = MagicMock(spec=stripe.Event)
    event.get = lambda key, default=None: {
        "type": event_type,
        "id": "evt_test_123",
        "data": {"object": obj},
    }.get(key, default)
    return event


def _make_user(user_id: str = "user-1"):
    user = MagicMock()
    user.id = user_id
    return user


# ---------------------------------------------------------------------------
# construct_webhook_event
# ---------------------------------------------------------------------------


class TestConstructWebhookEvent:
    def test_raises_when_webhook_secret_not_configured(self, settings_factory):
        handler = _make_handler(settings_factory, webhook_secret=None)
        with pytest.raises(BillingConfigurationError, match="webhook secret"):
            handler.construct_webhook_event(b"{}", "sig")

    def test_raises_when_signature_is_none(self, settings_factory):
        handler = _make_handler(settings_factory)
        with pytest.raises(BillingServiceError, match="Missing Stripe signature"):
            handler.construct_webhook_event(b"{}", None)

    def test_raises_on_invalid_payload(self, settings_factory, monkeypatch):
        handler = _make_handler(settings_factory)
        monkeypatch.setattr(
            stripe.Webhook,
            "construct_event",
            lambda *a, **kw: (_ for _ in ()).throw(ValueError("bad")),
        )
        with pytest.raises(BillingServiceError, match="Invalid Stripe webhook payload"):
            handler.construct_webhook_event(b"bad", "sig")

    def test_raises_on_signature_verification_error(self, settings_factory, monkeypatch):
        handler = _make_handler(settings_factory)

        def _raise(*args, **kwargs):
            raise stripe.error.SignatureVerificationError("bad sig", "sig")

        monkeypatch.setattr(stripe.Webhook, "construct_event", _raise)
        with pytest.raises(BillingServiceError, match="Invalid Stripe signature"):
            handler.construct_webhook_event(b"{}", "sig_bad")

    def test_succeeds_with_valid_event(self, settings_factory, monkeypatch):
        handler = _make_handler(settings_factory)
        mock_event = MagicMock(spec=stripe.Event)
        monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **kw: mock_event)
        result = handler.construct_webhook_event(b"payload", "sig_valid")
        assert result is mock_event


# ---------------------------------------------------------------------------
# handle_webhook_event - dispatch
# ---------------------------------------------------------------------------


class TestHandleWebhookEventDispatch:
    @pytest.mark.asyncio
    async def test_unhandled_event_is_ignored(self, settings_factory):
        handler = _make_handler(settings_factory)
        event = _make_event("payment_intent.created", {})
        # Should not raise
        await handler.handle_webhook_event(db=None, event=event)

    @pytest.mark.asyncio
    async def test_checkout_session_completed_dispatched(self, settings_factory):
        handler = _make_handler(settings_factory)
        called = []

        async def _fake_handler(db, event_id, obj):
            called.append(event_id)

        handler._handle_checkout_session_completed = _fake_handler
        event = _make_event("checkout.session.completed", {})
        await handler.handle_webhook_event(db=None, event=event)
        assert len(called) == 1

    @pytest.mark.asyncio
    async def test_invoice_payment_succeeded_dispatched(self, settings_factory):
        handler = _make_handler(settings_factory)
        called = []

        async def _fake_handler(db, event_id, obj):
            called.append(event_id)

        handler._handle_invoice_payment_succeeded = _fake_handler
        event = _make_event("invoice.payment_succeeded", {})
        await handler.handle_webhook_event(db=None, event=event)
        assert len(called) == 1

    @pytest.mark.asyncio
    async def test_subscription_deleted_dispatched(self, settings_factory):
        handler = _make_handler(settings_factory)
        called = []

        async def _fake_handler(db, event_id, obj):
            called.append(event_id)

        handler._handle_subscription_deleted = _fake_handler
        event = _make_event("customer.subscription.deleted", {})
        await handler.handle_webhook_event(db=None, event=event)
        assert len(called) == 1

    @pytest.mark.asyncio
    async def test_subscription_updated_dispatched(self, settings_factory):
        handler = _make_handler(settings_factory)
        called = []

        async def _fake_handler(db, event_id, obj):
            called.append(event_id)

        handler._handle_subscription_updated = _fake_handler
        event = _make_event("customer.subscription.updated", {})
        await handler.handle_webhook_event(db=None, event=event)
        assert len(called) == 1


# ---------------------------------------------------------------------------
# _claim_event and _finalize_transaction
# ---------------------------------------------------------------------------


class TestClaimEvent:
    @pytest.mark.asyncio
    async def test_claim_returns_true_for_new_event(self, settings_factory):
        billing_repo = _FakeBillingRepo()
        handler = _make_handler(settings_factory, billing_repo=billing_repo)
        result = await handler._claim_event(db=None, event_id="evt_1", user_id="u1")
        assert result is True
        assert len(billing_repo.claimed) == 1

    @pytest.mark.asyncio
    async def test_claim_returns_false_for_duplicate_event(self, settings_factory):
        billing_repo = _FakeBillingRepo()
        handler = _make_handler(settings_factory, billing_repo=billing_repo)
        result1 = await handler._claim_event(db=None, event_id="evt_dup", user_id="u1")
        result2 = await handler._claim_event(db=None, event_id="evt_dup", user_id="u1")
        assert result1 is True
        assert result2 is False
        assert len(billing_repo.claimed) == 1

    @pytest.mark.asyncio
    async def test_claim_allows_processing_when_event_id_is_none(self, settings_factory):
        billing_repo = _FakeBillingRepo()
        handler = _make_handler(settings_factory, billing_repo=billing_repo)
        result = await handler._claim_event(db=None, event_id=None, user_id="u1")
        assert result is True
        assert len(billing_repo.claimed) == 0


class TestFinalizeTransaction:
    @pytest.mark.asyncio
    async def test_updates_claimed_transaction(self, settings_factory):
        billing_repo = _FakeBillingRepo()
        handler = _make_handler(settings_factory, billing_repo=billing_repo)
        await handler._claim_event(db=None, event_id="evt_1", user_id="u1")
        await handler._finalize_transaction(
            db=None,
            event_id="evt_1",
            values={"status": "paid", "plan_id": "pro"},
        )
        assert len(billing_repo.updated) == 1
        assert billing_repo.events["evt_1"]["status"] == "paid"

    @pytest.mark.asyncio
    async def test_skips_when_event_id_is_none(self, settings_factory):
        billing_repo = _FakeBillingRepo()
        handler = _make_handler(settings_factory, billing_repo=billing_repo)
        await handler._finalize_transaction(
            db=None,
            event_id=None,
            values={"status": "paid"},
        )
        assert len(billing_repo.updated) == 0


# ---------------------------------------------------------------------------
# _resolve_subscription_context
# ---------------------------------------------------------------------------


class TestResolveSubscriptionContext:
    @pytest.mark.asyncio
    async def test_returns_context_without_subscription(self, settings_factory):
        handler = _make_handler(settings_factory)
        ctx = await handler._resolve_subscription_context(subscription_id=None)
        assert ctx.subscription is None
        assert ctx.user_id is None

    @pytest.mark.asyncio
    async def test_returns_context_with_subscription(self, settings_factory):
        handler = _make_handler(settings_factory)
        sub_dict = {
            "id": "sub_1",
            "metadata": {"user_id": "u1", "plan_id": "pro", "billing_cycle": "monthly"},
            "customer": "cus_1",
            "items": {
                "data": [
                    {
                        "current_period_end": 1999999999,
                        "price": {"id": "price_pro_m"},
                    }
                ]
            },
        }

        with patch.object(handler, "_retrieve_subscription", new=AsyncMock(return_value=sub_dict)):
            ctx = await handler._resolve_subscription_context(
                subscription_id="sub_1",
                user_id=None,
            )

        assert ctx.user_id == "u1"
        assert ctx.plan_id == "pro"
        assert ctx.customer_id == "cus_1"

    @pytest.mark.asyncio
    async def test_resolves_plan_from_price_id(self, settings_factory):
        handler = _make_handler(settings_factory)
        # price_pro_m is configured in test settings_factory
        sub_dict = {
            "metadata": {},
            "customer": "cus_1",
            "items": {
                "data": [
                    {
                        "current_period_end": 1999999999,
                        "price": {"id": "price_pro_m"},
                    }
                ]
            },
        }

        with patch.object(handler, "_retrieve_subscription", new=AsyncMock(return_value=sub_dict)):
            ctx = await handler._resolve_subscription_context(subscription_id="sub_1")

        assert ctx.plan_id == "pro"
        assert ctx.billing_cycle == "monthly"


# ---------------------------------------------------------------------------
# _handle_checkout_session_completed
# ---------------------------------------------------------------------------


class TestHandleCheckoutSessionCompleted:
    @pytest.mark.asyncio
    async def test_skips_when_no_user_id(self, settings_factory):
        user_repo = _FakeUserRepo()
        billing_repo = _FakeBillingRepo()
        handler = _make_handler(settings_factory, user_repo=user_repo, billing_repo=billing_repo)

        session_obj = {"metadata": {}, "subscription": None, "customer": "cus_1"}
        await handler._handle_checkout_session_completed(None, "evt_1", session_obj)
        assert len(billing_repo.claimed) == 0

    @pytest.mark.asyncio
    async def test_skips_when_user_not_found(self, settings_factory):
        user_repo = _FakeUserRepo(users={})  # no users
        billing_repo = _FakeBillingRepo()
        handler = _make_handler(settings_factory, user_repo=user_repo, billing_repo=billing_repo)

        session_obj = {
            "metadata": {"user_id": "missing-user", "plan_id": "pro"},
            "subscription": None,
            "customer": "cus_1",
            "status": "complete",
        }
        with patch.object(
            handler,
            "_resolve_subscription_context",
            new=AsyncMock(
                return_value=SubscriptionContext(
                    subscription=None,
                    user_id="missing-user",
                    plan_id="pro",
                    billing_cycle="monthly",
                    customer_id="cus_1",
                    period_end=None,
                    credits=100.0,
                )
            ),
        ):
            await handler._handle_checkout_session_completed(None, "evt_1", session_obj)
        # Event NOT claimed — user not found returns before claiming so
        # Stripe retries can succeed once the user exists.
        assert len(billing_repo.claimed) == 0

    @pytest.mark.asyncio
    async def test_updates_user_subscription_and_records_transaction(self, settings_factory):
        user = _make_user("user-1")
        user_repo = _FakeUserRepo(users={"user-1": user})
        billing_repo = _FakeBillingRepo()
        billing_customer_service = _FakeBillingCustomerService()
        handler = _make_handler(
            settings_factory,
            user_repo=user_repo,
            billing_repo=billing_repo,
            billing_customer_service=billing_customer_service,
        )

        session_obj = {
            "id": "cs_test_123",
            "metadata": {"user_id": "user-1", "plan_id": "pro", "billing_cycle": "monthly"},
            "subscription": "sub_1",
            "customer": "cus_1",
            "status": "complete",
        }

        ctx = SubscriptionContext(
            subscription={"status": "active"},
            user_id="user-1",
            plan_id="pro",
            billing_cycle="monthly",
            customer_id="cus_1",
            period_end=1999999999,
            credits=250.0,
        )

        with patch.object(
            handler, "_resolve_subscription_context", new=AsyncMock(return_value=ctx)
        ):
            await handler._handle_checkout_session_completed(None, "evt_1", session_obj)

        assert len(billing_customer_service.subscription_updates) == 1
        assert len(billing_repo.claimed) == 1
        assert billing_repo.claimed[0] == ("user-1", "evt_1")
        assert len(billing_repo.updated) == 1

    @pytest.mark.asyncio
    async def test_duplicate_event_skips_all_mutations(self, settings_factory):
        """Concurrent duplicate delivery: second call skips all business logic."""
        user = _make_user("user-1")
        user_repo = _FakeUserRepo(users={"user-1": user})
        billing_repo = _FakeBillingRepo()
        billing_customer_service = _FakeBillingCustomerService()
        handler = _make_handler(
            settings_factory,
            user_repo=user_repo,
            billing_repo=billing_repo,
            billing_customer_service=billing_customer_service,
        )

        session_obj = {
            "id": "cs_test_123",
            "metadata": {"user_id": "user-1", "plan_id": "pro", "billing_cycle": "monthly"},
            "subscription": "sub_1",
            "customer": "cus_1",
            "status": "complete",
        }

        ctx = SubscriptionContext(
            subscription={"status": "active"},
            user_id="user-1",
            plan_id="pro",
            billing_cycle="monthly",
            customer_id="cus_1",
            period_end=1999999999,
            credits=250.0,
        )

        with patch.object(
            handler, "_resolve_subscription_context", new=AsyncMock(return_value=ctx)
        ):
            await handler._handle_checkout_session_completed(None, "evt_dup", session_obj)
            await handler._handle_checkout_session_completed(None, "evt_dup", session_obj)

        # Only one subscription update should have happened
        assert len(billing_customer_service.subscription_updates) == 1
        assert len(billing_repo.claimed) == 1


# ---------------------------------------------------------------------------
# _handle_invoice_payment_succeeded
# ---------------------------------------------------------------------------


class TestHandleInvoicePaymentSucceeded:
    @pytest.mark.asyncio
    async def test_looks_up_user_by_customer_id_when_metadata_missing(self, settings_factory):
        user = _make_user("user-2")
        user_repo = _FakeUserRepo(users={"user-2": user})
        billing_repo = _FakeBillingRepo()
        billing_customer_service = _FakeBillingCustomerService()
        billing_customer_service.customers[("user-2", "stripe")] = {
            "user_id": "user-2",
            "provider": "stripe",
            "external_customer_id": "cus_2",
        }
        handler = _make_handler(
            settings_factory,
            user_repo=user_repo,
            billing_repo=billing_repo,
            billing_customer_service=billing_customer_service,
        )

        invoice_obj = {
            "id": "inv_1",
            "metadata": {},
            "subscription": None,
            "customer": "cus_2",
            "amount_paid": 2000,
            "currency": "usd",
            "status": "paid",
            "lines": {"data": []},
            "payment_intent": "pi_1",
        }

        ctx = SubscriptionContext(
            subscription=None,
            user_id=None,
            plan_id=None,
            billing_cycle=None,
            customer_id="cus_2",
            period_end=None,
            credits=None,
        )

        with patch.object(
            handler, "_resolve_subscription_context", new=AsyncMock(return_value=ctx)
        ):
            await handler._handle_invoice_payment_succeeded(None, "evt_2", invoice_obj)

        assert len(billing_customer_service.subscription_updates) == 1

    @pytest.mark.asyncio
    async def test_skips_when_no_user_found(self, settings_factory):
        user_repo = _FakeUserRepo()
        billing_repo = _FakeBillingRepo()
        handler = _make_handler(settings_factory, user_repo=user_repo, billing_repo=billing_repo)

        invoice_obj = {
            "id": "inv_2",
            "metadata": {},
            "subscription": None,
            "customer": "cus_unknown",
            "amount_paid": 0,
            "currency": "usd",
            "status": "paid",
            "lines": {"data": []},
            "payment_intent": None,
        }

        ctx = SubscriptionContext(
            subscription=None,
            user_id=None,
            plan_id=None,
            billing_cycle=None,
            customer_id="cus_unknown",
            period_end=None,
            credits=None,
        )

        with patch.object(
            handler, "_resolve_subscription_context", new=AsyncMock(return_value=ctx)
        ):
            await handler._handle_invoice_payment_succeeded(None, "evt_3", invoice_obj)

        assert len(billing_repo.claimed) == 0

    @pytest.mark.asyncio
    async def test_resolves_plan_from_line_items(self, settings_factory):
        user = _make_user("user-3")
        user_repo = _FakeUserRepo(users={"user-3": user})
        billing_repo = _FakeBillingRepo()
        billing_customer_service = _FakeBillingCustomerService()
        handler = _make_handler(
            settings_factory,
            user_repo=user_repo,
            billing_repo=billing_repo,
            billing_customer_service=billing_customer_service,
        )

        invoice_obj = {
            "id": "inv_3",
            "metadata": {"user_id": "user-3"},
            "subscription": None,
            "customer": "cus_3",
            "amount_paid": 1000,
            "currency": "usd",
            "status": "paid",
            "lines": {"data": [{"price": {"id": "price_plus_m"}}]},
            "payment_intent": None,
        }

        ctx = SubscriptionContext(
            subscription=None,
            user_id="user-3",
            plan_id=None,  # will be resolved from line items
            billing_cycle=None,
            customer_id="cus_3",
            period_end=None,
            credits=None,
        )

        with patch.object(
            handler, "_resolve_subscription_context", new=AsyncMock(return_value=ctx)
        ):
            await handler._handle_invoice_payment_succeeded(None, "evt_4", invoice_obj)

        # Plan should be resolved to 'plus' from price_plus_m
        assert len(billing_customer_service.subscription_updates) == 1
        sub_call = billing_customer_service.subscription_updates[0]
        assert sub_call.get("subscription_plan") == "plus"

    @pytest.mark.asyncio
    async def test_invoice_reset_preserves_unresolved_holds(self, settings_factory):
        user = _make_user("user-4")
        user_repo = _FakeUserRepo(users={"user-4": user})
        billing_repo = _FakeBillingRepo()
        billing_customer_service = _FakeBillingCustomerService()
        credit_service = SimpleNamespace(
            reset_plan_balance=AsyncMock(return_value=SimpleNamespace(updated=True)),
            clear_billing_status=AsyncMock(return_value=True),
        )
        reservation_repo = _FakeReservationRepo(
            held_regular=Decimal("7"),
            held_bonus=Decimal("2"),
        )
        handler = _make_handler(
            settings_factory,
            user_repo=user_repo,
            billing_repo=billing_repo,
            billing_customer_service=billing_customer_service,
            credit_service=credit_service,
            reservation_repo=reservation_repo,
        )

        invoice_obj = {
            "id": "inv_4",
            "metadata": {"user_id": "user-4"},
            "subscription": None,
            "customer": "cus_4",
            "amount_paid": 1500,
            "currency": "usd",
            "status": "paid",
            "lines": {"data": []},
            "payment_intent": "pi_4",
        }

        ctx = SubscriptionContext(
            subscription=None,
            user_id="user-4",
            plan_id="plus",
            billing_cycle="monthly",
            customer_id="cus_4",
            period_end=None,
            credits=100.0,
        )

        with patch.object(
            handler, "_resolve_subscription_context", new=AsyncMock(return_value=ctx)
        ):
            await handler._handle_invoice_payment_succeeded(None, "evt_5", invoice_obj)

        reset_call = credit_service.reset_plan_balance.await_args
        assert reset_call.args[1] == "user-4"
        assert reset_call.args[2] == 100.0
        credit_service.clear_billing_status.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_payment_replays_shortfall_failures_before_unblocking(self, settings_factory):
        user = _make_user("user-6")
        user_repo = _FakeUserRepo(users={"user-6": user})
        billing_repo = _FakeBillingRepo()
        billing_customer_service = _FakeBillingCustomerService()
        credit_service = SimpleNamespace(
            reset_plan_balance=AsyncMock(return_value=SimpleNamespace(updated=True)),
            clear_billing_status=AsyncMock(return_value=True),
        )
        reservation_repo = _FakeReservationRepo(
            replayable_shortfalls=[
                SimpleNamespace(
                    id="res-shortfall-1",
                    user_id="user-6",
                    status=ReservationStatus.SETTLEMENT_FAILED,
                )
            ]
        )

        async def _retry(db, *, reservation_id):
            reservation_repo.set_status(reservation_id, ReservationStatus.SETTLED)
            return SimpleNamespace(status=ReservationStatus.SETTLED)

        reservation_service = SimpleNamespace(
            retry_settlement_from_capture=AsyncMock(side_effect=_retry)
        )
        handler = _make_handler(
            settings_factory,
            user_repo=user_repo,
            billing_repo=billing_repo,
            billing_customer_service=billing_customer_service,
            credit_service=credit_service,
            reservation_repo=reservation_repo,
            reservation_service=reservation_service,
        )

        invoice_obj = {
            "id": "inv_6",
            "metadata": {"user_id": "user-6"},
            "subscription": None,
            "customer": "cus_6",
            "amount_paid": 1500,
            "currency": "usd",
            "status": "paid",
            "lines": {"data": []},
            "payment_intent": "pi_6",
        }

        ctx = SubscriptionContext(
            subscription=None,
            user_id="user-6",
            plan_id="plus",
            billing_cycle="monthly",
            customer_id="cus_6",
            period_end=None,
            credits=100.0,
        )

        with patch.object(
            handler, "_resolve_subscription_context", new=AsyncMock(return_value=ctx)
        ):
            await handler._handle_invoice_payment_succeeded(None, "evt_6", invoice_obj)

        reservation_service.retry_settlement_from_capture.assert_awaited_once_with(
            None,
            reservation_id="res-shortfall-1",
        )
        credit_service.clear_billing_status.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_payment_replays_all_shortfall_batches_before_unblocking(self, settings_factory):
        user = _make_user("user-6b")
        user_repo = _FakeUserRepo(users={"user-6b": user})
        billing_repo = _FakeBillingRepo()
        billing_customer_service = _FakeBillingCustomerService()
        credit_service = SimpleNamespace(
            reset_plan_balance=AsyncMock(return_value=SimpleNamespace(updated=True)),
            clear_billing_status=AsyncMock(return_value=True),
        )
        replayable_shortfalls = [
            SimpleNamespace(
                id=f"res-shortfall-batch-{index}",
                user_id="user-6b",
                status=ReservationStatus.SETTLEMENT_FAILED,
            )
            for index in range(51)
        ]
        reservation_repo = _FakeReservationRepo(replayable_shortfalls=replayable_shortfalls)

        async def _retry(db, *, reservation_id):
            reservation_repo.set_status(reservation_id, ReservationStatus.SETTLED)
            return SimpleNamespace(status=ReservationStatus.SETTLED)

        reservation_service = SimpleNamespace(
            retry_settlement_from_capture=AsyncMock(side_effect=_retry)
        )
        handler = _make_handler(
            settings_factory,
            user_repo=user_repo,
            billing_repo=billing_repo,
            billing_customer_service=billing_customer_service,
            credit_service=credit_service,
            reservation_repo=reservation_repo,
            reservation_service=reservation_service,
        )

        invoice_obj = {
            "id": "inv_6b",
            "metadata": {"user_id": "user-6b"},
            "subscription": None,
            "customer": "cus_6b",
            "amount_paid": 1500,
            "currency": "usd",
            "status": "paid",
            "lines": {"data": []},
            "payment_intent": "pi_6b",
        }

        ctx = SubscriptionContext(
            subscription=None,
            user_id="user-6b",
            plan_id="plus",
            billing_cycle="monthly",
            customer_id="cus_6b",
            period_end=None,
            credits=100.0,
        )

        with patch.object(
            handler, "_resolve_subscription_context", new=AsyncMock(return_value=ctx)
        ):
            await handler._handle_invoice_payment_succeeded(None, "evt_6b", invoice_obj)

        assert reservation_service.retry_settlement_from_capture.await_count == 51
        credit_service.clear_billing_status.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_payment_keeps_block_when_shortfall_replay_still_fails(self, settings_factory):
        user = _make_user("user-7")
        user_repo = _FakeUserRepo(users={"user-7": user})
        billing_repo = _FakeBillingRepo()
        billing_customer_service = _FakeBillingCustomerService()
        credit_service = SimpleNamespace(
            reset_plan_balance=AsyncMock(return_value=SimpleNamespace(updated=True)),
            clear_billing_status=AsyncMock(return_value=True),
        )
        reservation_repo = _FakeReservationRepo(
            replayable_shortfalls=[
                SimpleNamespace(
                    id="res-shortfall-2",
                    user_id="user-7",
                    status=ReservationStatus.SETTLEMENT_FAILED,
                )
            ]
        )
        reservation_service = SimpleNamespace(
            retry_settlement_from_capture=AsyncMock(
                return_value=SimpleNamespace(status=ReservationStatus.SETTLEMENT_FAILED)
            )
        )
        handler = _make_handler(
            settings_factory,
            user_repo=user_repo,
            billing_repo=billing_repo,
            billing_customer_service=billing_customer_service,
            credit_service=credit_service,
            reservation_repo=reservation_repo,
            reservation_service=reservation_service,
        )

        invoice_obj = {
            "id": "inv_7",
            "metadata": {"user_id": "user-7"},
            "subscription": None,
            "customer": "cus_7",
            "amount_paid": 1500,
            "currency": "usd",
            "status": "paid",
            "lines": {"data": []},
            "payment_intent": "pi_7",
        }

        ctx = SubscriptionContext(
            subscription=None,
            user_id="user-7",
            plan_id="plus",
            billing_cycle="monthly",
            customer_id="cus_7",
            period_end=None,
            credits=100.0,
        )

        with patch.object(
            handler, "_resolve_subscription_context", new=AsyncMock(return_value=ctx)
        ):
            await handler._handle_invoice_payment_succeeded(None, "evt_7", invoice_obj)

        reservation_service.retry_settlement_from_capture.assert_awaited_once_with(
            None,
            reservation_id="res-shortfall-2",
        )
        credit_service.clear_billing_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_payment_keeps_block_when_non_shortfall_failure_remains(self, settings_factory):
        user = _make_user("user-8a")
        user_repo = _FakeUserRepo(users={"user-8a": user})
        billing_repo = _FakeBillingRepo()
        billing_customer_service = _FakeBillingCustomerService()
        credit_service = SimpleNamespace(
            reset_plan_balance=AsyncMock(return_value=SimpleNamespace(updated=True)),
            clear_billing_status=AsyncMock(return_value=True),
        )
        reservation_repo = _FakeReservationRepo(
            replayable_shortfalls=[
                SimpleNamespace(
                    id="res-generic-failed",
                    user_id="user-8a",
                    status=ReservationStatus.SETTLEMENT_FAILED,
                    last_error="settle_exception",
                )
            ]
        )
        reservation_service = SimpleNamespace(
            retry_settlement_from_capture=AsyncMock(),
        )
        handler = _make_handler(
            settings_factory,
            user_repo=user_repo,
            billing_repo=billing_repo,
            billing_customer_service=billing_customer_service,
            credit_service=credit_service,
            reservation_repo=reservation_repo,
            reservation_service=reservation_service,
        )

        invoice_obj = {
            "id": "inv_8a",
            "metadata": {"user_id": "user-8a"},
            "subscription": None,
            "customer": "cus_8a",
            "amount_paid": 1500,
            "currency": "usd",
            "status": "paid",
            "lines": {"data": []},
            "payment_intent": "pi_8a",
        }

        ctx = SubscriptionContext(
            subscription=None,
            user_id="user-8a",
            plan_id="plus",
            billing_cycle="monthly",
            customer_id="cus_8a",
            period_end=None,
            credits=100.0,
        )

        with patch.object(
            handler, "_resolve_subscription_context", new=AsyncMock(return_value=ctx)
        ):
            await handler._handle_invoice_payment_succeeded(None, "evt_8a", invoice_obj)

        reservation_service.retry_settlement_from_capture.assert_not_awaited()
        credit_service.clear_billing_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_payment_replays_multiple_shortfall_batches_before_unblocking(
        self, settings_factory
    ):
        user = _make_user("user-8")
        user_repo = _FakeUserRepo(users={"user-8": user})
        billing_repo = _FakeBillingRepo()
        billing_customer_service = _FakeBillingCustomerService()
        credit_service = SimpleNamespace(
            reset_plan_balance=AsyncMock(return_value=SimpleNamespace(updated=True)),
            clear_billing_status=AsyncMock(return_value=True),
        )
        reservation_repo = _FakeReservationRepo(
            replayable_shortfalls=[
                SimpleNamespace(
                    id=f"res-shortfall-{idx}",
                    user_id="user-8",
                    status=ReservationStatus.SETTLEMENT_FAILED,
                )
                for idx in range(51)
            ]
        )

        async def _retry(db, *, reservation_id):
            reservation_repo.set_status(reservation_id, ReservationStatus.SETTLED)
            return SimpleNamespace(status=ReservationStatus.SETTLED)

        reservation_service = SimpleNamespace(
            retry_settlement_from_capture=AsyncMock(side_effect=_retry)
        )
        handler = _make_handler(
            settings_factory,
            user_repo=user_repo,
            billing_repo=billing_repo,
            billing_customer_service=billing_customer_service,
            credit_service=credit_service,
            reservation_repo=reservation_repo,
            reservation_service=reservation_service,
        )

        invoice_obj = {
            "id": "inv_8",
            "metadata": {"user_id": "user-8"},
            "subscription": None,
            "customer": "cus_8",
            "amount_paid": 1500,
            "currency": "usd",
            "status": "paid",
            "lines": {"data": []},
            "payment_intent": "pi_8",
        }

        ctx = SubscriptionContext(
            subscription=None,
            user_id="user-8",
            plan_id="plus",
            billing_cycle="monthly",
            customer_id="cus_8",
            period_end=None,
            credits=100.0,
        )

        with patch.object(
            handler, "_resolve_subscription_context", new=AsyncMock(return_value=ctx)
        ):
            await handler._handle_invoice_payment_succeeded(None, "evt_8", invoice_obj)

        assert reservation_service.retry_settlement_from_capture.await_count == 51
        credit_service.clear_billing_status.assert_awaited_once()


# ---------------------------------------------------------------------------
# _handle_subscription_deleted
# ---------------------------------------------------------------------------


class TestHandleSubscriptionDeleted:
    @pytest.mark.asyncio
    async def test_cancels_subscription(self, settings_factory):
        user = _make_user("user-4")
        user_repo = _FakeUserRepo(users={"user-4": user})
        billing_repo = _FakeBillingRepo()
        billing_customer_service = _FakeBillingCustomerService()
        credit_service = SimpleNamespace(
            reset_plan_balance=AsyncMock(return_value=SimpleNamespace(updated=True))
        )
        handler = _make_handler(
            settings_factory,
            user_repo=user_repo,
            billing_repo=billing_repo,
            billing_customer_service=billing_customer_service,
            credit_service=credit_service,
        )

        sub_obj = {
            "id": "sub_del_1",
            "metadata": {"user_id": "user-4"},
            "customer": "cus_4",
            "status": "canceled",
            "current_period_end": 1999999999,
            "canceled_at": None,
            "items": {"data": [{"plan": {"interval": "month"}}]},
        }

        await handler._handle_subscription_deleted(None, "evt_5", sub_obj)

        assert len(billing_customer_service.subscription_updates) == 1
        assert (
            billing_customer_service.customers[("user-4", "stripe")]["external_customer_id"]
            == "cus_4"
        )
        reset_call = credit_service.reset_plan_balance.await_args
        assert reset_call.args[1] == "user-4"
        assert reset_call.args[2] == handler._stripe_config.plan_credits("free")
        sub = billing_customer_service.subscription_updates[0]
        assert sub.get("subscription_plan") == "free"
        assert sub.get("subscription_status") == "canceled"

    @pytest.mark.asyncio
    async def test_looks_up_user_by_customer_when_no_metadata(self, settings_factory):
        user = _make_user("user-5")
        user_repo = _FakeUserRepo(users={"user-5": user})
        billing_repo = _FakeBillingRepo()
        billing_customer_service = _FakeBillingCustomerService()
        billing_customer_service.customers[("user-5", "stripe")] = {
            "user_id": "user-5",
            "provider": "stripe",
            "external_customer_id": "cus_5",
        }
        handler = _make_handler(
            settings_factory,
            user_repo=user_repo,
            billing_repo=billing_repo,
            billing_customer_service=billing_customer_service,
        )

        sub_obj = {
            "id": "sub_del_2",
            "metadata": {},
            "customer": "cus_5",
            "status": "canceled",
            "current_period_end": None,
            "canceled_at": 1700000000,
            "items": {"data": []},
        }

        await handler._handle_subscription_deleted(None, "evt_6", sub_obj)
        assert len(billing_customer_service.subscription_updates) == 1

    @pytest.mark.asyncio
    async def test_skips_when_no_user_id(self, settings_factory):
        user_repo = _FakeUserRepo()
        billing_repo = _FakeBillingRepo()
        handler = _make_handler(settings_factory, user_repo=user_repo, billing_repo=billing_repo)

        sub_obj = {
            "id": "sub_del_3",
            "metadata": {},
            "customer": "cus_unknown",
            "status": "canceled",
            "current_period_end": None,
            "canceled_at": None,
            "items": {"data": []},
        }

        await handler._handle_subscription_deleted(None, "evt_7", sub_obj)
        assert len(billing_repo.claimed) == 0

    @pytest.mark.asyncio
    async def test_uses_canceled_at_if_no_period_end(self, settings_factory):
        user = _make_user("user-6")
        user_repo = _FakeUserRepo(users={"user-6": user})
        billing_repo = _FakeBillingRepo()
        billing_customer_service = _FakeBillingCustomerService()
        handler = _make_handler(
            settings_factory,
            user_repo=user_repo,
            billing_repo=billing_repo,
            billing_customer_service=billing_customer_service,
        )

        sub_obj = {
            "id": "sub_del_4",
            "metadata": {"user_id": "user-6"},
            "customer": "cus_6",
            "status": "canceled",
            "current_period_end": None,
            "canceled_at": 1700000000,
            "items": {"data": []},
        }

        await handler._handle_subscription_deleted(None, "evt_8", sub_obj)
        sub = billing_customer_service.subscription_updates[0]
        assert sub.get("subscription_current_period_end") is not None


# ---------------------------------------------------------------------------
# _handle_subscription_updated
# ---------------------------------------------------------------------------


class TestHandleSubscriptionUpdated:
    @pytest.mark.asyncio
    async def test_updates_subscription_plan_from_price(self, settings_factory):
        user = _make_user("user-7")
        user_repo = _FakeUserRepo(users={"user-7": user})
        billing_repo = _FakeBillingRepo()
        billing_customer_service = _FakeBillingCustomerService()
        handler = _make_handler(
            settings_factory,
            user_repo=user_repo,
            billing_repo=billing_repo,
            billing_customer_service=billing_customer_service,
        )

        sub_obj = {
            "id": "sub_upd_1",
            "metadata": {"user_id": "user-7"},
            "customer": "cus_7",
            "status": "active",
            "current_period_end": 1999999999,
            "items": {
                "data": [
                    {"price": {"id": "price_pro_m", "recurring": {"interval": "month"}}, "plan": {}}
                ]
            },
        }

        await handler._handle_subscription_updated(None, "evt_9", sub_obj)

        assert len(billing_customer_service.subscription_updates) == 1
        sub = billing_customer_service.subscription_updates[0]
        assert sub.get("subscription_plan") == "pro"

    @pytest.mark.asyncio
    async def test_skips_when_user_id_not_found(self, settings_factory):
        user_repo = _FakeUserRepo(users={})
        billing_repo = _FakeBillingRepo()
        handler = _make_handler(settings_factory, user_repo=user_repo, billing_repo=billing_repo)

        sub_obj = {
            "id": "sub_upd_2",
            "metadata": {},
            "customer": "cus_unknown",
            "status": "active",
            "current_period_end": None,
            "items": {"data": []},
        }

        await handler._handle_subscription_updated(None, "evt_10", sub_obj)
        assert len(billing_repo.claimed) == 0

    @pytest.mark.asyncio
    async def test_falls_back_to_recurring_interval_for_billing_cycle(self, settings_factory):
        user = _make_user("user-8")
        user_repo = _FakeUserRepo(users={"user-8": user})
        billing_repo = _FakeBillingRepo()
        billing_customer_service = _FakeBillingCustomerService()
        handler = _make_handler(
            settings_factory,
            user_repo=user_repo,
            billing_repo=billing_repo,
            billing_customer_service=billing_customer_service,
        )

        sub_obj = {
            "id": "sub_upd_3",
            "metadata": {"user_id": "user-8"},
            "customer": "cus_8",
            "status": "active",
            "current_period_end": 1999999999,
            "items": {
                "data": [
                    {
                        "price": {"id": "price_unknown", "recurring": {"interval": "year"}},
                        "plan": {},
                    }
                ]
            },
        }

        await handler._handle_subscription_updated(None, "evt_11", sub_obj)

        sub = billing_customer_service.subscription_updates[0]
        assert sub.get("subscription_billing_cycle") == "annually"

    @pytest.mark.asyncio
    async def test_falls_back_to_plan_interval(self, settings_factory):
        user = _make_user("user-9")
        user_repo = _FakeUserRepo(users={"user-9": user})
        billing_repo = _FakeBillingRepo()
        billing_customer_service = _FakeBillingCustomerService()
        handler = _make_handler(
            settings_factory,
            user_repo=user_repo,
            billing_repo=billing_repo,
            billing_customer_service=billing_customer_service,
        )

        sub_obj = {
            "id": "sub_upd_4",
            "metadata": {"user_id": "user-9"},
            "customer": "cus_9",
            "status": "active",
            "current_period_end": 1999999999,
            "items": {
                "data": [
                    {
                        "price": {"id": "price_unknown", "recurring": {}},
                        "plan": {"interval": "month"},
                    }
                ]
            },
        }

        await handler._handle_subscription_updated(None, "evt_12", sub_obj)

        sub = billing_customer_service.subscription_updates[0]
        assert sub.get("subscription_billing_cycle") == "monthly"

    @pytest.mark.asyncio
    async def test_looks_up_user_by_customer_id(self, settings_factory):
        user = _make_user("user-10")
        user_repo = _FakeUserRepo(users={"user-10": user})
        billing_repo = _FakeBillingRepo()
        billing_customer_service = _FakeBillingCustomerService()
        billing_customer_service.customers[("user-10", "stripe")] = {
            "user_id": "user-10",
            "provider": "stripe",
            "external_customer_id": "cus_10",
        }
        handler = _make_handler(
            settings_factory,
            user_repo=user_repo,
            billing_repo=billing_repo,
            billing_customer_service=billing_customer_service,
        )

        sub_obj = {
            "id": "sub_upd_5",
            "metadata": {},
            "customer": "cus_10",
            "status": "active",
            "current_period_end": 1999999999,
            "items": {"data": [{"price": {"id": "price_pro_m", "recurring": {}}, "plan": {}}]},
        }

        await handler._handle_subscription_updated(None, "evt_13", sub_obj)
        assert len(billing_customer_service.subscription_updates) == 1

    @pytest.mark.asyncio
    async def test_records_transaction_for_update(self, settings_factory):
        user = _make_user("user-11")
        user_repo = _FakeUserRepo(users={"user-11": user})
        billing_repo = _FakeBillingRepo()
        handler = _make_handler(settings_factory, user_repo=user_repo, billing_repo=billing_repo)

        sub_obj = {
            "id": "sub_upd_6",
            "metadata": {"user_id": "user-11"},
            "customer": "cus_11",
            "status": "active",
            "current_period_end": 1999999999,
            "items": {"data": [{"price": {"id": "price_pro_m", "recurring": {}}, "plan": {}}]},
        }

        await handler._handle_subscription_updated(None, "evt_14", sub_obj)
        assert len(billing_repo.claimed) == 1
        assert billing_repo.claimed[0] == ("user-11", "evt_14")
        assert len(billing_repo.updated) == 1


# ---------------------------------------------------------------------------
# SubscriptionContext dataclass
# ---------------------------------------------------------------------------


class TestSubscriptionContext:
    def test_can_be_created(self):
        ctx = SubscriptionContext(
            subscription={"status": "active"},
            user_id="u1",
            plan_id="pro",
            billing_cycle="monthly",
            customer_id="cus_1",
            period_end=1999999999,
            credits=250.0,
        )
        assert ctx.user_id == "u1"
        assert ctx.plan_id == "pro"
        assert ctx.credits == 250.0

    def test_all_fields_can_be_none(self):
        ctx = SubscriptionContext(
            subscription=None,
            user_id=None,
            plan_id=None,
            billing_cycle=None,
            customer_id=None,
            period_end=None,
            credits=None,
        )
        assert ctx.subscription is None
        assert ctx.credits is None
