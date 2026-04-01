"""Pydantic schemas (DTOs) for llm_settings domain."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from typing import Optional
from uuid import UUID

from .types import Provider
from ii_agent.settings.llm.types import ConfigType


# ---------------------------------------------------------------------------
# Nested JSONB schemas
# ---------------------------------------------------------------------------


class ModelParams(BaseModel):
    """Provider-specific settings stored in the ``configs`` JSONB column."""

    max_retries: int = Field(default=3)
    max_message_chars: int = Field(default=30000)
    temperature: float = Field(default=0.0)
    thinking_tokens: int = Field(default=16000)
    # Vertex AI
    vertex_region: str | None = None
    vertex_project_id: str | None = None
    # Azure
    azure_endpoint: str | None = None
    azure_api_version: str | None = None
    # Flags
    cot_model: bool = False


class PricingInfo(BaseModel):
    """Pricing stored in the ``pricing`` JSONB column."""

    input_price_per_million: float = Field(
        default=0.0, description="Price per million input tokens in USD"
    )
    output_price_per_million: float = Field(
        default=0.0, description="Price per million output tokens in USD"
    )
    cache_write_price_per_million: float = Field(
        default=0.0, description="Price per million cache write tokens"
    )
    cache_read_price_per_million: float = Field(
        default=0.0, description="Price per million cache read tokens"
    )


class ModelConfigEntry(BaseModel):
    """A single model configuration entry for seeding.

    Used in ``MODEL_CONFIGS`` env var (JSON list) or ``MODEL_CONFIGS_FILE``
    (YAML list). Maps directly to a ``ModelSetting`` DB row.
    """

    model_id: str
    provider: Provider
    api_key: str | None = None
    base_url: str | None = None
    display_name: str | None = None
    is_default: bool = False
    params: ModelParams = Field(default_factory=ModelParams)
    pricing: PricingInfo | None = None


class ModelConfig(BaseModel):
    """Resolved model configuration for agent / LLM provider construction.

    Built from a ``ModelSetting`` DB row.  Carries everything needed to
    instantiate an LLM provider: credentials, endpoint, provider-specific
    params, and pricing.
    """

    id: UUID
    model_id: str
    provider: Provider
    api_key: SecretStr | None = None
    base_url: str | None = None
    display_name: str | None = None
    params: ModelParams = Field(default_factory=ModelParams)
    pricing: PricingInfo | None = None
    config_type: ConfigType = ConfigType.SYSTEM

    def is_user_model(self) -> bool:
        """Return True when the config originates from a user-provided key."""
        return self.config_type == ConfigType.USER

    @property
    def setting_id(self) -> str:
        """Backward-compatible string ID used by callers that expect ``str``."""
        return str(self.id)

    # Convenience accessors that mirror legacy LLMConfig field names so that
    # consumer code (agent factory, model utils) can migrate incrementally.
    @property
    def model(self) -> str:
        return self.model_id

    @property
    def temperature(self) -> float:
        return self.params.temperature

    @property
    def max_retries(self) -> int:
        return self.params.max_retries

    @property
    def max_message_chars(self) -> int:
        return self.params.max_message_chars

    @property
    def thinking_tokens(self) -> int:
        return self.params.thinking_tokens

    @property
    def vertex_region(self) -> str | None:
        return self.params.vertex_region

    @property
    def vertex_project_id(self) -> str | None:
        return self.params.vertex_project_id

    @property
    def azure_endpoint(self) -> str | None:
        return self.params.azure_endpoint

    @property
    def azure_api_version(self) -> str | None:
        return self.params.azure_api_version

    @property
    def cot_model(self) -> bool:
        return self.params.cot_model


# ---------------------------------------------------------------------------
# Create / Update DTOs
# ---------------------------------------------------------------------------


class ModelSettingCreate(BaseModel):
    """Input for creating / upserting an LLM model setting."""

    model_id: str = Field(..., description="Model identifier (e.g. 'claude-sonnet-4-6')")
    provider: str = Field(..., description="Provider name (Anthropic, OpenAI, Google, Custom)")
    api_key: str = Field(..., description="API key for the model")
    base_url: str | None = Field(None, description="Base URL for API endpoint")
    display_name: str | None = Field(None, description="Human-readable label")
    configs: ModelParams | None = Field(None, description="Provider-specific settings")
    pricing: PricingInfo | None = Field(None, description="Token pricing info")
    config_type: ConfigType = Field(default=ConfigType.USER)
    is_default: bool = Field(default=False)
    is_active: bool = Field(default=True)


class ModelSettingUpdate(BaseModel):
    """Input for partial-updating an existing LLM model setting."""

    api_key: str | None = None
    base_url: str | None = None
    display_name: str | None = None
    configs: ModelParams | None = None
    pricing: PricingInfo | None = None
    config_type: ConfigType | None = None
    is_default: bool | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Response DTOs
# ---------------------------------------------------------------------------


class ModelSettingInfo(BaseModel):
    """LLM model setting response (no sensitive data)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model_id: str
    provider: str
    base_url: str | None = None
    display_name: str | None = None
    configs: ModelParams | None = None
    pricing: PricingInfo | None = None
    config_type: ConfigType
    is_default: bool
    is_active: bool
    has_api_key: bool
    created_at: str
    updated_at: str | None = None


class ModelSettingInfoWithKey(ModelSettingInfo):
    """LLM model setting response (includes decrypted API key)."""

    api_key: str | None = None


class ModelSettingList(BaseModel):
    """Wrapper for listing model settings."""

    models: list[ModelSettingInfo]

    def get_by_id(self, setting_id: str) -> ModelSettingInfo | None:
        return next(
            (s for s in self.models if str(s.id) == setting_id),
            None,
        )

    def get_by_model(self, model_id: str) -> ModelSettingInfo | None:
        return next(
            (s for s in self.models if s.model_id == model_id),
            None,
        )


# ---------------------------------------------------------------------------
# Unified model list (system + user)
# ---------------------------------------------------------------------------


class LLMModelInfo(BaseModel):
    """Combined model info for the "all available models" endpoint."""

    id: UUID
    model_id: str
    model: str = ""  # Alias for model_id, used by FE
    provider: str
    display_name: str | None = None
    source: str = "system"
    base_url: str | None = None
    pricing: PricingInfo | None = None


class LLMModelList(BaseModel):
    """Response for listing all available models."""

    models: list[LLMModelInfo]


