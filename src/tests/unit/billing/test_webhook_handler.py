from types import SimpleNamespace

import pytest
import stripe

from ii_agent.billing.exceptions import BillingConfigurationError, BillingServiceError
from ii_agent.billing.stripe_config import StripeConfig
from ii_agent.billing.webhook_handler import StripeWebhookHandler


class FakeBillingRepo:
    def __init__(self):
        self.events = {}
        self.created = []

    async def get_by_event_id(self, db, event_id):
        return self.events.get(event_id)

    async def create(self, db, user_id, stripe_event_id, **values):
        self.events[stripe_event_id] = {"user_id": user_id, **values}
        self.created.append((user_id, stripe_event_id, values))


class FakeUserRepo:
    async def get_by_id(self, db, user_id):
        return None

    async def lookup_by_customer_id(self, db, customer_id):
        return None


def _build_handler(settings_factory, webhook_secret="whsec_123"):
    settings = settings_factory(stripe={"webhook_secret": webhook_secret})
    return StripeWebhookHandler(
        stripe_config=StripeConfig(config=settings),
        billing_repo=FakeBillingRepo(),
        user_repo=FakeUserRepo(),
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
async def test_record_transaction_is_idempotent(settings_factory):
    handler = _build_handler(settings_factory)

    await handler._record_transaction(
        db=None,
        event_id="evt_1",
        user_id="u1",
        values={"status": "paid"},
    )
    await handler._record_transaction(
        db=None,
        event_id="evt_1",
        user_id="u1",
        values={"status": "paid"},
    )

    assert len(handler._billing_repo.created) == 1
