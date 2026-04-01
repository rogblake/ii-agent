"""FastAPI dependencies for credits domain."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep
from ii_agent.credits.service import CreditService


def _get_credit_service(container: ContainerDep) -> CreditService:
    return container.credit_service


CreditServiceDep = Annotated[CreditService, Depends(_get_credit_service)]
