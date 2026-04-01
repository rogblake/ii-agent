"""LLM configuration domain module."""

from .dependencies import ModelSettingServiceDep
from .exceptions import LLMSettingNotFoundError
from .models import ModelSetting
from .repository import ModelSettingRepository
from .router import router
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
from .service import ModelSettingService, get_system_model_config_from_db
from .types import ConfigType

__all__ = [
    # Types
    "ConfigType",
    # Models
    "ModelSetting",
    # Repository
    "ModelSettingRepository",
    # Service
    "ModelSettingService",
    "get_system_model_config_from_db",
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
    # Dependencies
    "ModelSettingServiceDep",
    # Exceptions
    "LLMSettingNotFoundError",
    # Router
    "router",
]
