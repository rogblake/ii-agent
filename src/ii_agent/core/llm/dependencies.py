"""FastAPI dependencies for core LLM billing and config resolution."""

from typing import Annotated

from fastapi import Depends

from ii_agent.billing.credits.dependencies import CreditServiceDep
from ii_agent.billing.outbox.dependencies import BillingUsageFactServiceDep
from ii_agent.billing.reservations.dependencies import CreditReservationServiceDep
from ii_agent.billing.usage.dependencies import (
    LLMInvocationRepositoryDep,
    UsageServiceDep,
)
from ii_agent.core.dependencies import SettingsDep
from ii_agent.settings.llm.dependencies import LLMSettingServiceDep
from ii_agent.core.llm.billing_service import LLMBillingService
from ii_agent.core.llm.config_resolver import LLMConfigResolver
from ii_agent.core.llm.execution_service import LLMExecutionService


def get_llm_billing_service(
    usage_service: UsageServiceDep,
    credit_service: CreditServiceDep,
    reservation_service: CreditReservationServiceDep,
    settings: SettingsDep,
    outbox_service: BillingUsageFactServiceDep,
) -> LLMBillingService:
    """Provide LLMBillingService instance."""
    return LLMBillingService(
        usage_service=usage_service,
        credit_service=credit_service,
        reservation_service=reservation_service,
        config=settings,
        outbox_service=outbox_service,
    )


def get_llm_config_resolver(
    llm_setting_service: LLMSettingServiceDep,
    settings: SettingsDep,
) -> LLMConfigResolver:
    """Provide LLMConfigResolver instance."""
    return LLMConfigResolver(llm_setting_service=llm_setting_service, config=settings)


LLMBillingServiceDep = Annotated[LLMBillingService, Depends(get_llm_billing_service)]
LLMConfigResolverDep = Annotated[LLMConfigResolver, Depends(get_llm_config_resolver)]


def get_llm_execution_service(
    llm_billing: LLMBillingServiceDep,
    llm_invocation_repo: LLMInvocationRepositoryDep,
) -> LLMExecutionService:
    """Provide LLMExecutionService instance."""
    return LLMExecutionService(
        llm_billing=llm_billing,
        llm_invocation_repo=llm_invocation_repo,
    )


LLMExecutionServiceDep = Annotated[
    LLMExecutionService,
    Depends(get_llm_execution_service),
]
