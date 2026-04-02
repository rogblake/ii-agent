"""Credit calculation models using v1 model ID conventions.

Model IDs follow the v1 models convention from src/ii_agent/v1/models/:
- Anthropic: claude-sonnet-4-5-*, claude-opus-4-5-*, etc.
- OpenAI: gpt-4o, o1, o3, etc.
- Google: gemini-2.0-flash-*, gemini-2.5-*, gemini-3-*, etc.
"""

from typing import Dict, Optional
from pydantic import BaseModel, Field

from ii_agent.engine.types import Provider


class ModelPricing(BaseModel):
    """Pricing information for different LLM models."""

    model_id: str = Field(description="Model ID matching v1 model definitions")
    provider: Optional[Provider] = Field(
        default=None, description="Provider (Anthropic, OpenAI, Google, etc.)"
    )
    input_price_per_million: float = Field(
        description="Price per million input tokens in USD"
    )
    output_price_per_million: float = Field(
        description="Price per million output tokens in USD"
    )
    cache_write_price_per_million: float = Field(
        default=0.0, description="Price per million cache write tokens"
    )
    cache_read_price_per_million: float = Field(
        default=0.0, description="Price per million cache read tokens"
    )

    @classmethod
    def get_default_pricing(
        cls, model_id: str, provider: Optional[Provider] = None
    ) -> "ModelPricing":
        """Get default pricing for common models.

        Args:
            model_id: The model ID (e.g., "claude-sonnet-4-5-20250929")
            provider: Optional provider name for disambiguation

        Returns:
            ModelPricing with appropriate pricing for the model
        """
        pricing_map: Dict[str, "ModelPricing"] = {
            # ===== Anthropic Claude Models =====
            # Matching v1 model IDs: claude-sonnet-4-5-*, claude-opus-4-5-*
            "claude-opus-4-6": cls(
                model_id="claude-opus-4-6",
                provider=Provider.ANTHROPIC,
                input_price_per_million=5.0,
                output_price_per_million=25.0,
                cache_write_price_per_million=6.25,
                cache_read_price_per_million=0.5,
            ),
            "claude-opus-4-5": cls(
                model_id="claude-opus-4-5",
                provider=Provider.ANTHROPIC,
                input_price_per_million=5.0,
                output_price_per_million=25.0,
                cache_write_price_per_million=6.25,
                cache_read_price_per_million=0.5,
            ),
            "claude-sonnet-4-5": cls(
                model_id="claude-sonnet-4-5",
                provider=Provider.ANTHROPIC,
                input_price_per_million=3.0,
                output_price_per_million=15.0,
                cache_write_price_per_million=3.75,
                cache_read_price_per_million=0.3,
            ),
            "claude-sonnet-4": cls(
                model_id="claude-sonnet-4",
                provider=Provider.ANTHROPIC,
                input_price_per_million=3.0,
                output_price_per_million=15.0,
                cache_write_price_per_million=3.75,
                cache_read_price_per_million=0.3,
            ),
            "claude-opus-4": cls(
                model_id="claude-opus-4",
                provider=Provider.ANTHROPIC,
                input_price_per_million=15.0,
                output_price_per_million=75.0,
                cache_write_price_per_million=18.75,
                cache_read_price_per_million=1.5,
            ),
            "claude-3-5-haiku": cls(
                model_id="claude-3-5-haiku",
                provider=Provider.ANTHROPIC,
                input_price_per_million=0.8,
                output_price_per_million=4.0,
                cache_write_price_per_million=1.0,
                cache_read_price_per_million=0.08,
            ),
            # ===== OpenAI Models =====
            # Matching v1 model IDs: gpt-4o, o1, o3, etc.
            "gpt-4o": cls(
                model_id="gpt-4o",
                provider=Provider.OPENAI,
                input_price_per_million=2.5,
                output_price_per_million=10.0,
                cache_read_price_per_million=1.25,
            ),
            "gpt-4o-mini": cls(
                model_id="gpt-4o-mini",
                provider=Provider.OPENAI,
                input_price_per_million=0.15,
                output_price_per_million=0.6,
                cache_read_price_per_million=0.075,
            ),
            "o1": cls(
                model_id="o1",
                provider=Provider.OPENAI,
                input_price_per_million=15.0,
                output_price_per_million=60.0,
                cache_read_price_per_million=7.5,
            ),
            "o1-mini": cls(
                model_id="o1-mini",
                provider=Provider.OPENAI,
                input_price_per_million=1.1,
                output_price_per_million=4.4,
                cache_read_price_per_million=0.55,
            ),
            "o3": cls(
                model_id="o3",
                provider=Provider.OPENAI,
                input_price_per_million=10.0,
                output_price_per_million=40.0,
                cache_read_price_per_million=2.5,
            ),
            "o3-mini": cls(
                model_id="o3-mini",
                provider=Provider.OPENAI,
                input_price_per_million=1.1,
                output_price_per_million=4.4,
                cache_read_price_per_million=0.55,
            ),
            # ===== Google Gemini Models =====
            # Matching v1 model IDs: gemini-2.0-flash-*, gemini-2.5-*, gemini-3-*
            "gemini-2.5-pro": cls(
                model_id="gemini-2.5-pro",
                provider=Provider.GOOGLE,
                input_price_per_million=1.25,
                output_price_per_million=10.0,
            ),
            "gemini-2.5-flash": cls(
                model_id="gemini-2.5-flash",
                provider=Provider.GOOGLE,
                input_price_per_million=0.15,
                output_price_per_million=0.6,
            ),
            "gemini-2.0-flash": cls(
                model_id="gemini-2.0-flash",
                provider=Provider.GOOGLE,
                input_price_per_million=0.1,
                output_price_per_million=0.4,
            ),
            "gemini-3-pro-preview": cls(
                model_id="gemini-3-pro-preview",
                provider=Provider.GOOGLE,
                input_price_per_million=2.0,
                output_price_per_million=12.0,
            ),
            "gemini-3-flash-preview": cls(
                model_id="gemini-3-flash-preview",
                provider=Provider.GOOGLE,
                input_price_per_million=0.5,
                output_price_per_million=3.0,
            ),
            # ===== DeepSeek Models =====
            "deepseek-reasoner": cls(
                model_id="deepseek-reasoner",
                provider=Provider.CUSTOM,
                input_price_per_million=0.55,
                output_price_per_million=2.19,
                cache_read_price_per_million=0.14,
            ),
            "deepseek-chat": cls(
                model_id="deepseek-chat",
                provider=Provider.CUSTOM,
                input_price_per_million=0.27,
                output_price_per_million=1.1,
                cache_read_price_per_million=0.07,
            ),
        }

        normalized_id = model_id.lower()

        # Try exact match
        if normalized_id in pricing_map:
            return pricing_map[normalized_id]

        # Try prefix matching (handles versioned IDs like "claude-sonnet-4-5-20250929")
        for pattern, pricing in pricing_map.items():
            if normalized_id.startswith(pattern):
                return cls(
                    model_id=model_id,
                    provider=pricing.provider,
                    input_price_per_million=pricing.input_price_per_million,
                    output_price_per_million=pricing.output_price_per_million,
                    cache_write_price_per_million=pricing.cache_write_price_per_million,
                    cache_read_price_per_million=pricing.cache_read_price_per_million,
                )

        # Provider-based defaults
        if provider:
            provider_defaults = {
                Provider.ANTHROPIC: cls(
                    model_id=model_id,
                    provider=Provider.ANTHROPIC,
                    input_price_per_million=3.0,
                    output_price_per_million=15.0,
                    cache_write_price_per_million=3.75,
                    cache_read_price_per_million=0.3,
                ),
                Provider.OPENAI: cls(
                    model_id=model_id,
                    provider=Provider.OPENAI,
                    input_price_per_million=2.5,
                    output_price_per_million=10.0,
                    cache_read_price_per_million=1.25,
                ),
                Provider.GOOGLE: cls(
                    model_id=model_id,
                    provider=Provider.GOOGLE,
                    input_price_per_million=0.15,
                    output_price_per_million=0.6,
                ),
            }
            if provider in provider_defaults:
                return provider_defaults[provider]

        # Default pricing (conservative estimate)
        return cls(
            model_id=model_id,
            provider=provider,
            input_price_per_million=2.5,
            output_price_per_million=10.0,
            cache_read_price_per_million=1.25,
        )
