"""FastAPI dependencies for llm_settings domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep
from ii_agent.settings.llm.service import ModelSettingService


def _get_model_setting_service(container: ContainerDep) -> ModelSettingService:
    return container.model_setting_service


ModelSettingServiceDep = Annotated[ModelSettingService, Depends(_get_model_setting_service)]
