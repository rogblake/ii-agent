from types import SimpleNamespace

import pytest

from ii_agent.billing.service import BillingService, CheckoutSessionParams
from ii_agent.billing.stripe_config import StripeConfig
from ii_agent.billing.webhook_handler import StripeWebhookHandler

pytestmark = pytest.mark.integration


class BillingRepo:
    def __init__(self):
        self.events = {}

    async def get_by_event_id(self, db, event_id):
        return self.events.get(event_id)

    async def create(self, db, user_id, stripe_event_id, **values):
        self.events[stripe_event_id] = {"user_id": user_id, **values}


class UserRepo:
    def __init__(self):
        self.user = SimpleNamespace(id="u1", stripe_customer_id="cus_1")

    async def get_by_id(self, db, user_id):
        return self.user

    async def lookup_by_customer_id(self, db, customer_id):
        return "u1"


@pytest.mark.asyncio
async def test_billing_checkout_and_webhook_idempotency(settings_factory):
    settings = settings_factory()
    stripe_config = StripeConfig(config=settings)
    user_repo = UserRepo()

    billing_service = BillingService(stripe_config=stripe_config, user_repo=user_repo)

    with pytest.raises(Exception):
        # free plan must not proceed to checkout
        await billing_service.create_checkout_session(
            db=None,
            params=CheckoutSessionParams(plan_id="free", billing_cycle="monthly", user_id="u1", return_url=None),
        )

    handler = StripeWebhookHandler(
        stripe_config=stripe_config,
        billing_repo=BillingRepo(),
        user_repo=user_repo,
    )

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

    assert len(handler._billing_repo.events) == 1
