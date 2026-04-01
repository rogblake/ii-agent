"""Unit tests for BillingCustomerService."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.skip(
    "BillingCustomerService was removed during billing refactoring",
    allow_module_level=True,
)

from ii_agent.billing.customers.models import BillingCustomer  # noqa: E402
from ii_agent.billing.customers.repository import BillingCustomerRepository  # noqa: E402
from ii_agent.billing.customers.service import BillingCustomerService  # noqa: E402

pytestmark = pytest.mark.unit

_USER_ID = str(uuid.uuid4())
_CUSTOMER_ID = "cus_stripe_123"


class FakeCustomerRepo:
    def __init__(self):
        self.customers: dict[tuple[str, str], dict] = {}
        self.created: list = []
        self.updated: list = []

    async def get_by_user(self, db, user_id, provider="stripe"):
        data = self.customers.get((user_id, provider))
        if data:
            return SimpleNamespace(**data)
        return None

    async def get_by_external_id(self, db, provider, external_customer_id):
        for key, data in self.customers.items():
            if key[1] == provider and data["external_customer_id"] == external_customer_id:
                return SimpleNamespace(**data)
        return None

    async def list_by_user_ids(self, db, user_ids, provider="stripe"):
        return [
            SimpleNamespace(**data)
            for (data_user_id, data_provider), data in self.customers.items()
            if data_provider == provider and data_user_id in user_ids
        ]

    async def list_by_subscription(
        self,
        db,
        *,
        provider="stripe",
        subscription_statuses=None,
        subscription_billing_cycle=None,
    ):
        status_values = set(subscription_statuses or [])
        return [
            SimpleNamespace(**data)
            for (_, data_provider), data in self.customers.items()
            if data_provider == provider
            and (not status_values or data.get("subscription_status") in status_values)
            and (
                subscription_billing_cycle is None
                or data.get("subscription_billing_cycle") == subscription_billing_cycle
            )
        ]

    async def create(self, db, *, user_id, provider, external_customer_id, **kwargs):
        data = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "provider": provider,
            "external_customer_id": external_customer_id,
            **kwargs,
        }
        self.customers[(user_id, provider)] = data
        self.created.append(data)
        return SimpleNamespace(**data)

    async def update_subscription(self, db, customer, **fields):
        self.updated.append({"customer": customer, **fields})
        for key, value in fields.items():
            if value is not ...:
                setattr(customer, key, value)

    async def lookup_user_id_by_customer_id(self, db, external_customer_id, provider="stripe"):
        for key, data in self.customers.items():
            if key[1] == provider and data["external_customer_id"] == external_customer_id:
                return data["user_id"]
        return None


def _make_service(repo=None) -> BillingCustomerService:
    return BillingCustomerService(customer_repo=repo or FakeCustomerRepo())


# ---------------------------------------------------------------------------
# get_or_create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_create_creates_new_customer():
    """Creates a new BillingCustomer when none exists."""
    repo = FakeCustomerRepo()
    svc = _make_service(repo)

    result = await svc.get_or_create(None, user_id=_USER_ID, external_customer_id=_CUSTOMER_ID)

    assert result.user_id == _USER_ID
    assert result.external_customer_id == _CUSTOMER_ID
    assert len(repo.created) == 1


@pytest.mark.asyncio
async def test_get_or_create_returns_existing_customer():
    """Returns existing BillingCustomer when one exists."""
    repo = FakeCustomerRepo()
    repo.customers[(_USER_ID, "stripe")] = {
        "id": "existing-id",
        "user_id": _USER_ID,
        "provider": "stripe",
        "external_customer_id": _CUSTOMER_ID,
    }
    svc = _make_service(repo)

    result = await svc.get_or_create(None, user_id=_USER_ID, external_customer_id=_CUSTOMER_ID)

    assert result.id == "existing-id"
    assert len(repo.created) == 0


# ---------------------------------------------------------------------------
# update_subscription
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_subscription_updates_fields():
    """Updates subscription fields on existing customer."""
    repo = FakeCustomerRepo()
    repo.customers[(_USER_ID, "stripe")] = {
        "id": "cust-id",
        "user_id": _USER_ID,
        "provider": "stripe",
        "external_customer_id": _CUSTOMER_ID,
        "subscription_plan": "free",
        "subscription_status": None,
    }
    svc = _make_service(repo)

    result = await svc.update_subscription(
        None,
        _USER_ID,
        subscription_plan="pro",
        subscription_status="active",
    )

    assert result is not None
    assert len(repo.updated) == 1


@pytest.mark.asyncio
async def test_update_subscription_returns_none_when_not_found():
    """Returns None when no billing customer found."""
    svc = _make_service()

    result = await svc.update_subscription(
        None,
        "nonexistent-user",
        subscription_plan="pro",
    )

    assert result is None


# ---------------------------------------------------------------------------
# lookup_user_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lookup_user_id_found():
    """Returns user_id when customer exists."""
    repo = FakeCustomerRepo()
    repo.customers[(_USER_ID, "stripe")] = {
        "user_id": _USER_ID,
        "provider": "stripe",
        "external_customer_id": _CUSTOMER_ID,
    }
    svc = _make_service(repo)

    result = await svc.lookup_user_id(None, _CUSTOMER_ID)
    assert result == _USER_ID


@pytest.mark.asyncio
async def test_lookup_user_id_not_found():
    """Returns None when customer doesn't exist."""
    svc = _make_service()

    result = await svc.lookup_user_id(None, "cus_nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_list_by_user_ids_returns_map():
    """Returns billing customers keyed by user_id."""
    repo = FakeCustomerRepo()
    repo.customers[(_USER_ID, "stripe")] = {
        "user_id": _USER_ID,
        "provider": "stripe",
        "external_customer_id": _CUSTOMER_ID,
    }
    svc = _make_service(repo)

    result = await svc.list_by_user_ids(None, [_USER_ID, "missing-user"])

    assert list(result) == [_USER_ID]
    assert result[_USER_ID].external_customer_id == _CUSTOMER_ID


@pytest.mark.asyncio
async def test_list_by_subscription_filters_rows():
    """Lists billing customers using subscription filters."""
    repo = FakeCustomerRepo()
    repo.customers[(_USER_ID, "stripe")] = {
        "user_id": _USER_ID,
        "provider": "stripe",
        "external_customer_id": _CUSTOMER_ID,
        "subscription_status": "active",
        "subscription_billing_cycle": "annually",
    }
    repo.customers[("other-user", "stripe")] = {
        "user_id": "other-user",
        "provider": "stripe",
        "external_customer_id": "cus_other",
        "subscription_status": "canceled",
        "subscription_billing_cycle": "annually",
    }
    svc = _make_service(repo)

    result = await svc.list_by_subscription(
        None,
        subscription_statuses={"active", "trialing"},
        subscription_billing_cycle="annually",
    )

    assert [customer.user_id for customer in result] == [_USER_ID]


def test_resolve_effective_profile_reads_only_from_billing_customer():
    """Uses billing_customers only when resolving the effective profile."""
    svc = _make_service()
    customer = SimpleNamespace(
        external_customer_id="cus_new",
        subscription_plan="pro",
        subscription_status=None,
        subscription_billing_cycle=None,
        subscription_current_period_end=None,
    )

    result = svc.resolve_effective_profile(customer=customer)

    assert result.external_customer_id == "cus_new"
    assert result.subscription_plan == "pro"
    assert result.subscription_status is None
    assert result.subscription_billing_cycle is None
    assert result.subscription_current_period_end is None


def test_resolve_effective_profile_no_customer():
    """Returns all None when no billing_customer exists."""
    svc = _make_service()

    result = svc.resolve_effective_profile(customer=None)

    assert result.external_customer_id is None
    assert result.subscription_plan is None
    assert result.subscription_status is None


def test_resolve_effective_profile_ignores_legacy_user_fields():
    svc = _make_service()
    user = SimpleNamespace(
        subscription_plan="pro",
        subscription_status="active",
        subscription_billing_cycle="annually",
        subscription_current_period_end="period-end",
    )

    result = svc.resolve_effective_profile(customer=None, user=user)

    assert result.external_customer_id is None
    assert result.subscription_plan is None
    assert result.subscription_status is None
    assert result.subscription_billing_cycle is None
    assert result.subscription_current_period_end is None
