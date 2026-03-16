"""FastAPI dependencies for usage domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.billing.credits.dependencies import CreditServiceDep
from ii_agent.billing.usage.llm_invocation_repository import LLMInvocationRepository
from ii_agent.billing.usage.repository import MetricsRepository
from ii_agent.billing.usage.service import UsageService
from ii_agent.billing.usage.tool_invocation_repository import ToolInvocationRepository
from ii_agent.billing.usage.usage_record_repository import UsageRecordRepository


def get_metrics_repository() -> MetricsRepository:
    """Provide MetricsRepository instance."""
    return MetricsRepository()


MetricsRepositoryDep = Annotated[MetricsRepository, Depends(get_metrics_repository)]


def get_usage_record_repository() -> UsageRecordRepository:
    """Provide UsageRecordRepository instance."""
    return UsageRecordRepository()


UsageRecordRepositoryDep = Annotated[
    UsageRecordRepository,
    Depends(get_usage_record_repository),
]


def get_llm_invocation_repository() -> LLMInvocationRepository:
    """Provide LLMInvocationRepository instance."""
    return LLMInvocationRepository()


LLMInvocationRepositoryDep = Annotated[
    LLMInvocationRepository,
    Depends(get_llm_invocation_repository),
]


def get_tool_invocation_repository() -> ToolInvocationRepository:
    """Provide ToolInvocationRepository instance."""
    return ToolInvocationRepository()


ToolInvocationRepositoryDep = Annotated[
    ToolInvocationRepository,
    Depends(get_tool_invocation_repository),
]


def get_usage_service(
    credit_service: CreditServiceDep,
    metrics_repo: MetricsRepositoryDep,
    usage_record_repo: UsageRecordRepositoryDep,
) -> UsageService:
    """Provide UsageService instance."""
    return UsageService(
        credit_service=credit_service,
        metrics_repo=metrics_repo,
        usage_record_repo=usage_record_repo,
    )


UsageServiceDep = Annotated[UsageService, Depends(get_usage_service)]
