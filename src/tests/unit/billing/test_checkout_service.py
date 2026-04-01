from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import stripe

from ii_agent.billing.exceptions import BillingServiceError, BillingUnsupportedPlanError
from ii_agent.billing.schemas import CreateCheckoutParams, CreatePortalParams
from ii_agent.billing.service import BillingService


@pytest.mark.asyncio
async def test_create_checkout_session_rejects_free_plan(settings_factory):
    service = BillingService(settings=settings_factory())

    with pytest.raises(BillingUnsupportedPlanError):
        await service.create_checkout_session(
            CreateCheckoutParams(
                plan_id="free",
                billing_cycle="monthly",
                user_id="u1",
                return_url="https://app.local",
            ),
        )


@pytest.mark.asyncio
async def test_create_checkout_session_reuses_existing_customer(monkeypatch, settings_factory):
    settings = settings_factory()
    service = BillingService(settings=settings)

    captured = {}

    def _create_session(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="cs_123")

    async def _run_in_threadpool(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr("ii_agent.billing.service.run_in_threadpool", _run_in_threadpool)
    monkeypatch.setattr(stripe.checkout.Session, "create", _create_session)

    user = SimpleNamespace(id="u1", stripe_customer_id="cus_123")
    service._get_user = AsyncMock(return_value=user)

    await service.create_checkout_session(
        CreateCheckoutParams(
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
    service = BillingService(settings=settings_factory())

    user = SimpleNamespace(id="u1", stripe_customer_id=None)
    service._get_user = AsyncMock(return_value=user)

    with pytest.raises(BillingServiceError, match="Stripe customer"):
        await service.create_portal_session(
            CreatePortalParams(user_id="u1"),
        )


@pytest.mark.asyncio
async def test_create_checkout_session_uses_customer_from_user(
    monkeypatch, settings_factory
):
    settings = settings_factory()
    service = BillingService(settings=settings)

    captured = {}

    def _create_session(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="cs_456")

    async def _run_in_threadpool(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr("ii_agent.billing.service.run_in_threadpool", _run_in_threadpool)
    monkeypatch.setattr(stripe.checkout.Session, "create", _create_session)

    user = SimpleNamespace(id="u1", stripe_customer_id="cus_from_user")
    service._get_user = AsyncMock(return_value=user)

    await service.create_checkout_session(
        CreateCheckoutParams(
            plan_id="plus",
            billing_cycle="monthly",
            user_id="u1",
            return_url="https://app.local",
        ),
    )

    assert captured["customer"] == "cus_from_user"
