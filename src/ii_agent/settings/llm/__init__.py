"""LLM configuration domain module.

Services and dependencies are accessed via DI — import from their
own modules or use the Dep aliases in settings/llm/dependencies.py.
Router is registered in app/routers.py.
"""

from .exceptions import LLMSettingNotFoundError
from .models import ModelSetting
from .repository import ModelSettingRepository
from .schemas import (
    ModelConfig,
    ModelParams,
    LLMModelInfo,
    LLMModelList,
    ModelSettingCreate,
    ModelSettingInfo,
    ModelSettingInfoWithKey,
    ModelSettingList,
    ModelSettingUpdate,
    PricingInfo,
)
from .types import ConfigType, Provider

__all__ = [
    # Types
    "ConfigType",
    "Provider",
    # Models
    "ModelSetting",
    # Repository
    "ModelSettingRepository",
    # Schemas
    "ModelConfig",
    "ModelParams",
    "LLMModelInfo",
    "LLMModelList",
    "ModelSettingCreate",
    "ModelSettingInfo",
    "ModelSettingInfoWithKey",
    "ModelSettingList",
    "ModelSettingUpdate",
    "PricingInfo",
    # Exceptions
    "LLMSettingNotFoundError",
]
