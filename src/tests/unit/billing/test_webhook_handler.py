from types import SimpleNamespace

import pytest
import stripe

from ii_agent.billing.exceptions import BillingConfigurationError, BillingServiceError
from ii_agent.billing.stripe_config import StripeConfig
from ii_agent.billing.webhook_handler import StripeWebhookHandler


class FakeBillingRepo:
    def __init__(self):
        self.events = {}
        self.claimed = []
        self.updated = []

    async def get_by_event_id(self, db, event_id):
        return self.events.get(event_id)

    async def claim_event(self, db, *, user_id, stripe_event_id):
        if stripe_event_id in self.events:
            return False
        self.events[stripe_event_id] = {"user_id": user_id, "status": "processing"}
        self.claimed.append((user_id, stripe_event_id))
        return True

    async def update_by_event_id(self, db, *, stripe_event_id, **values):
        self.events[stripe_event_id].update(values)
        self.updated.append((stripe_event_id, values))


class FakeUserRepo:
    async def get_by_id(self, db, user_id):
        return None

    async def lookup_by_customer_id(self, db, customer_id):
        return None


class FakeBillingCustomerService:
    async def get_or_create(self, db, *, user_id, provider="stripe", external_customer_id, **kwargs):
        return None

    async def update_subscription(self, db, user_id, *, provider="stripe", **kwargs):
        return None

    async def lookup_user_id(self, db, external_customer_id, provider="stripe"):
        return None


def _build_handler(settings_factory, webhook_secret="whsec_123"):
    settings = settings_factory(stripe={"webhook_secret": webhook_secret})
    return StripeWebhookHandler(
        stripe_config=StripeConfig(config=settings),
        billing_repo=FakeBillingRepo(),
        user_repo=FakeUserRepo(),
        billing_customer_service=FakeBillingCustomerService(),
    )


def test_construct_webhook_event_requires_secret(settings_factory):
    handler = _build_handler(settings_factory, webhook_secret=None)

    with pytest.raises(BillingConfigurationError):
        handler.construct_webhook_event(b"{}", "sig")


def test_construct_webhook_event_requires_signature(settings_factory):
    handler = _build_handler(settings_factory)

    with pytest.raises(BillingServiceError, match="Missing Stripe signature"):
        handler.construct_webhook_event(b"{}", None)


def test_construct_webhook_event_rejects_invalid_payload(monkeypatch, settings_factory):
    handler = _build_handler(settings_factory)

    def _raise_payload(*args, **kwargs):
        raise ValueError("bad")

    monkeypatch.setattr(stripe.Webhook, "construct_event", _raise_payload)

    with pytest.raises(BillingServiceError, match="Invalid Stripe webhook payload"):
        handler.construct_webhook_event(b"{}", "sig")


@pytest.mark.asyncio
async def test_claim_event_is_idempotent(settings_factory):
    handler = _build_handler(settings_factory)

    first = await handler._claim_event(db=None, event_id="evt_1", user_id="u1")
    second = await handler._claim_event(db=None, event_id="evt_1", user_id="u1")

    assert first is True
    assert second is False
    assert len(handler._billing_repo.claimed) == 1


@pytest.mark.asyncio
async def test_finalize_transaction_updates_claimed_event(settings_factory):
    handler = _build_handler(settings_factory)

    claimed = await handler._claim_event(db=None, event_id="evt_1", user_id="u1")
    assert claimed is True

    await handler._finalize_transaction(
        db=None,
        event_id="evt_1",
        values={"status": "paid"},
    )

    assert handler._billing_repo.events["evt_1"]["status"] == "paid"
