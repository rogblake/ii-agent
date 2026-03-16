from types import SimpleNamespace

import pytest
import stripe

from ii_agent.billing.exceptions import BillingServiceError, BillingUnsupportedPlanError
from ii_agent.billing.customers.service import BillingCustomerService
from ii_agent.billing.service import BillingService, CheckoutSessionParams
from ii_agent.billing.stripe_config import StripeConfig


class FakeUserRepo:
    def __init__(self, user=None):
        self.user = user

    async def get_by_id(self, db, user_id):
        return self.user


class FakeBillingCustomerService:
    def __init__(self, customer=None):
        self.customer = customer
        self.created = []

    async def get_by_user(self, db, user_id, *, provider="stripe"):
        return self.customer

    async def get_or_create(self, db, *, user_id, provider="stripe", external_customer_id, **kwargs):
        self.created.append((user_id, provider, external_customer_id))
        return SimpleNamespace(
            user_id=user_id,
            provider=provider,
            external_customer_id=external_customer_id,
        )


@pytest.mark.asyncio
async def test_create_checkout_session_rejects_free_plan(settings_factory):
    stripe_config = StripeConfig(config=settings_factory())
    service = BillingService(
        stripe_config=stripe_config,
        user_repo=FakeUserRepo(),
        billing_customer_service=FakeBillingCustomerService(),
    )

    with pytest.raises(BillingUnsupportedPlanError):
        await service.create_checkout_session(
            db=None,
            params=CheckoutSessionParams(
                plan_id="free",
                billing_cycle="monthly",
                user_id="u1",
                return_url="https://app.local",
            ),
        )


@pytest.mark.asyncio
async def test_create_checkout_session_reuses_existing_customer(monkeypatch, settings_factory):
    settings = settings_factory()
    stripe_config = StripeConfig(config=settings)

    captured = {}

    def _create_session(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="cs_123")

    async def _run_in_threadpool(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr("ii_agent.billing.service.run_in_threadpool", _run_in_threadpool)
    monkeypatch.setattr(stripe.checkout.Session, "create", _create_session)

    user = SimpleNamespace(id="u1")
    customer = SimpleNamespace(external_customer_id="cus_123")
    service = BillingService(
        stripe_config=stripe_config,
        user_repo=FakeUserRepo(user=user),
        billing_customer_service=FakeBillingCustomerService(customer=customer),
    )

    await service.create_checkout_session(
        db=None,
        params=CheckoutSessionParams(
            plan_id="plus",
            billing_cycle="monthly",
            user_id="u1",
            return_url="https://app.local",
        ),
    )

    assert captured["customer"] == "cus_123"
    assert captured["metadata"]["plan_id"] == "plus"
    assert captured["automatic_tax"] == {"enabled": True}


@pytest.mark.asyncio
async def test_create_portal_session_requires_customer(settings_factory):
    stripe_config = StripeConfig(config=settings_factory())
    service = BillingService(
        stripe_config=stripe_config,
        user_repo=FakeUserRepo(user=SimpleNamespace(id="u1")),
        billing_customer_service=FakeBillingCustomerService(),
    )

    with pytest.raises(BillingServiceError, match="Stripe customer"):
        await service.create_portal_session(db=None, user_id="u1")


@pytest.mark.asyncio
async def test_create_checkout_session_prefers_billing_customer_table(monkeypatch, settings_factory):
    settings = settings_factory()
    stripe_config = StripeConfig(config=settings)

    captured = {}

    def _create_session(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="cs_456")

    async def _run_in_threadpool(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr("ii_agent.billing.service.run_in_threadpool", _run_in_threadpool)
    monkeypatch.setattr(stripe.checkout.Session, "create", _create_session)

    billing_customer_service = FakeBillingCustomerService(
        customer=SimpleNamespace(external_customer_id="cus_from_new_table")
    )
    service = BillingService(
        stripe_config=stripe_config,
        user_repo=FakeUserRepo(user=SimpleNamespace(id="u1")),
        billing_customer_service=billing_customer_service,
    )

    await service.create_checkout_session(
        db=None,
        params=CheckoutSessionParams(
            plan_id="plus",
            billing_cycle="monthly",
            user_id="u1",
            return_url="https://app.local",
        ),
    )

    assert captured["customer"] == "cus_from_new_table"
