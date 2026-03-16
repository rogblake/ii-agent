from types import SimpleNamespace

import pytest

from ii_agent.billing.customers.service import BillingCustomerService
from ii_agent.billing.customers.repository import BillingCustomerRepository
from ii_agent.billing.service import BillingService, CheckoutSessionParams
from ii_agent.billing.stripe_config import StripeConfig
from ii_agent.billing.webhook_handler import StripeWebhookHandler

pytestmark = pytest.mark.integration


class BillingRepo:
    def __init__(self):
        self.events = {}

    async def get_by_event_id(self, db, event_id):
        return self.events.get(event_id)

    async def claim_event(self, db, *, user_id, stripe_event_id):
        if stripe_event_id in self.events:
            return False
        self.events[stripe_event_id] = {"user_id": user_id, "status": "processing"}
        return True

    async def update_by_event_id(self, db, *, stripe_event_id, **values):
        if stripe_event_id in self.events:
            self.events[stripe_event_id].update(values)

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
    billing_customer_service = BillingCustomerService(
        customer_repo=BillingCustomerRepository()
    )

    billing_service = BillingService(
        stripe_config=stripe_config,
        user_repo=user_repo,
        billing_customer_service=billing_customer_service,
    )

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
        billing_customer_service=billing_customer_service,
    )

    # Test atomic claim idempotency
    claimed1 = await handler._claim_event(db=None, event_id="evt_1", user_id="u1")
    claimed2 = await handler._claim_event(db=None, event_id="evt_1", user_id="u1")

    assert claimed1 is True
    assert claimed2 is False
    assert len(handler._billing_repo.events) == 1
