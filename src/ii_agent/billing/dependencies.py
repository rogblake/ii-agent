"""FastAPI dependencies for billing domain."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from ii_agent.billing.service import BillingService
from ii_agent.core.dependencies import ContainerDep


def _get_billing_service(container: ContainerDep) -> BillingService:
    return container.billing_service


BillingServiceDep = Annotated[BillingService, Depends(_get_billing_service)]
