"""FastAPI dependencies for core LLM billing and config resolution."""

from typing import Annotated

from fastapi import Depends

from ii_agent.billing.credits.dependencies import CreditServiceDep
from ii_agent.core.dependencies import SettingsDep
from ii_agent.settings.llm.dependencies import LLMSettingServiceDep
from ii_agent.core.llm.billing_service import LLMBillingService
from ii_agent.core.llm.config_resolver import LLMConfigResolver


def get_llm_billing_service(
    credit_service: CreditServiceDep,
    settings: SettingsDep,
) -> LLMBillingService:
    """Provide LLMBillingService instance."""
    return LLMBillingService(credit_service=credit_service, config=settings)


def get_llm_config_resolver(
    llm_setting_service: LLMSettingServiceDep,
    settings: SettingsDep,
) -> LLMConfigResolver:
    """Provide LLMConfigResolver instance."""
    return LLMConfigResolver(llm_setting_service=llm_setting_service, config=settings)


LLMBillingServiceDep = Annotated[LLMBillingService, Depends(get_llm_billing_service)]
LLMConfigResolverDep = Annotated[LLMConfigResolver, Depends(get_llm_config_resolver)]
