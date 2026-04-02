"""Pricing configuration for image generation providers.

This module centralizes all pricing information for different models and providers.
Adding a new model is as simple as adding a new entry to the appropriate pricing dictionary.
"""

from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class TokenPricing:
    """Pricing for token-based models (e.g., OpenAI, Vertex GenAI)."""

    input_text_per_million: float = 0.0
    output_text_per_million: float = 0.0
    input_image_per_million: float = 0.0
    output_image_per_million: float = 0.0


@dataclass
class FixedPricing:
    """Fixed pricing per image generation (e.g., Vertex Imagen)."""

    price_per_image: float


# OpenAI Model Pricing
# Docs: https://openai.com/api/pricing/
OPENAI_PRICING: Dict[str, TokenPricing] = {
    "gpt-image-1.5": TokenPricing(
        input_text_per_million=5.00,
        output_text_per_million=10.00,
        input_image_per_million=8.00,
        output_image_per_million=32.00,
    ),
}


# Vertex AI Model Pricing
# Docs: https://cloud.google.com/vertex-ai/generative-ai/pricing

# Imagen models (fixed price per image)
VERTEX_IMAGEN_PRICING: Dict[str, FixedPricing] = {
    "imagen-4.0-generate-001": FixedPricing(price_per_image=0.04),
}


# GenAI models (token-based pricing)
# Docs: https://cloud.google.com/vertex-ai/generative-ai/pricing
VERTEX_GENAI_PRICING: Dict[str, TokenPricing] = {
    "gemini-3-pro-image-preview": TokenPricing(
        input_text_per_million=2.00,
        output_text_per_million=12.00,
        input_image_per_million=2.00,
        output_image_per_million=120.00,
    ),
    "gemini-3.1-flash-image-preview": TokenPricing(
        input_text_per_million=0.50,
        output_text_per_million=3.00,
        input_image_per_million=0.50,
        output_image_per_million=60.00,
    ),
}


def get_openai_pricing(model_name: str) -> TokenPricing:
    """Get pricing for an OpenAI model.

    Args:
        model_name: Name of the OpenAI model

    Returns:
        TokenPricing configuration for the model

    Raises:
        ValueError: If the model is not found in the pricing configuration
    """
    if model_name not in OPENAI_PRICING:
        available_models = list(OPENAI_PRICING.keys())
        raise ValueError(
            f"Unknown OpenAI model '{model_name}'. "
            f"Please add pricing for this model in pricing.py. "
            f"Available models: {available_models}"
        )
    return OPENAI_PRICING[model_name]


def calculate_openai_cost(
    model_name: str,
    input_text_tokens: int = 0,
    output_text_tokens: int = 0,
    input_image_tokens: int = 0,
    output_image_tokens: int = 0,
) -> float:
    """Calculate cost for OpenAI image generation.

    Args:
        model_name: Name of the model
        input_text_tokens: Number of input text tokens
        output_text_tokens: Number of output text tokens
        input_image_tokens: Number of input image tokens
        output_image_tokens: Number of output image tokens

    Returns:
        Total cost in USD
    """
    pricing = get_openai_pricing(model_name)

    cost = (
        input_text_tokens * pricing.input_text_per_million / 1_000_000
        + output_text_tokens * pricing.output_text_per_million / 1_000_000
        + input_image_tokens * pricing.input_image_per_million / 1_000_000
        + output_image_tokens * pricing.output_image_per_million / 1_000_000
    )

    return cost


def get_vertex_imagen_pricing(model_name: str) -> FixedPricing:
    """Get pricing for a Vertex Imagen model.

    Args:
        model_name: Name of the Imagen model

    Returns:
        FixedPricing configuration for the model

    Raises:
        ValueError: If the model is not found in the pricing configuration
    """
    if model_name not in VERTEX_IMAGEN_PRICING:
        available_models = list(VERTEX_IMAGEN_PRICING.keys())
        raise ValueError(
            f"Unknown Vertex Imagen model '{model_name}'. "
            f"Please add pricing for this model in pricing.py. "
            f"Available models: {available_models}"
        )
    return VERTEX_IMAGEN_PRICING[model_name]


def calculate_vertex_imagen_cost(model_name: str) -> float:
    """Calculate cost for Vertex Imagen generation.

    Args:
        model_name: Name of the Imagen model

    Returns:
        Cost per image in USD
    """
    pricing = get_vertex_imagen_pricing(model_name)
    return pricing.price_per_image


def get_vertex_genai_pricing(model_name: str) -> TokenPricing:
    """Get pricing for a Vertex GenAI model.

    Args:
        model_name: Name of the GenAI model

    Returns:
        TokenPricing configuration for the model

    Raises:
        ValueError: If the model is not found in the pricing configuration
    """
    if model_name not in VERTEX_GENAI_PRICING:
        available_models = list(VERTEX_GENAI_PRICING.keys())
        raise ValueError(
            f"Unknown Vertex GenAI model '{model_name}'. "
            f"Please add pricing for this model in pricing.py. "
            f"Available models: {available_models}"
        )
    return VERTEX_GENAI_PRICING[model_name]


def calculate_vertex_genai_cost(
    model_name: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    *,
    input_text_tokens: int = 0,
    output_text_tokens: int = 0,
    input_image_tokens: int = 0,
    output_image_tokens: int = 0,
    fallback_input_tokens: int = 0,
    fallback_output_tokens: int = 0,
) -> float:
    """Calculate cost for Vertex GenAI image generation.

    Args:
        model_name: Name of the GenAI model
        input_tokens: Aggregate input tokens (legacy/fallback usage)
        output_tokens: Aggregate output tokens (legacy/fallback usage)
        input_text_tokens: Number of text tokens in the prompt
        output_text_tokens: Number of text tokens in the response
        input_image_tokens: Number of image tokens in the prompt
        output_image_tokens: Number of image tokens in the response
        fallback_input_tokens: Aggregate input tokens when modality details are unavailable
        fallback_output_tokens: Aggregate output tokens when modality details are unavailable

    Returns:
        Total cost in USD
    """
    pricing = get_vertex_genai_pricing(model_name)

    # Prefer modality-specific billing if available.
    if any(
        (
            input_text_tokens,
            output_text_tokens,
            input_image_tokens,
            output_image_tokens,
        )
    ):
        return (
            input_text_tokens * pricing.input_text_per_million / 1_000_000
            + output_text_tokens * pricing.output_text_per_million / 1_000_000
            + input_image_tokens * pricing.input_image_per_million / 1_000_000
            + output_image_tokens * pricing.output_image_per_million / 1_000_000
        )

    # If explicit fallback totals are provided, use those.
    if fallback_input_tokens or fallback_output_tokens:
        return (
            fallback_input_tokens * pricing.input_text_per_million / 1_000_000
            + fallback_output_tokens * pricing.output_text_per_million / 1_000_000
        )

    # Backward-compatible behavior for existing callers.
    return (
        input_tokens * pricing.input_text_per_million / 1_000_000
        + output_tokens * pricing.output_text_per_million / 1_000_000
    )
