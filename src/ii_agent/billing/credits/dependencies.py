"""FastAPI dependencies for credits domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.auth.users.dependencies import UserRepositoryDep
from ii_agent.billing.credits.service import CreditService
from ii_agent.billing.usage.repository import MetricsRepository


def get_metrics_repository() -> MetricsRepository:
    """Provide MetricsRepository instance."""
    return MetricsRepository()


MetricsRepositoryDep = Annotated[MetricsRepository, Depends(get_metrics_repository)]


def get_credit_service(
    user_repo: UserRepositoryDep,
    metrics_repo: MetricsRepositoryDep,
) -> CreditService:
    """Provide CreditService instance with explicit repo injection."""
    return CreditService(user_repo=user_repo, metrics_repo=metrics_repo)


CreditServiceDep = Annotated[CreditService, Depends(get_credit_service)]
