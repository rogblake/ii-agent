from ii_agent.billing.credits.pricing import ModelPricing
from ii_agent.engine.types import Provider


def test_pricing_exact_and_prefix_model_match():
    exact = ModelPricing.get_default_pricing("gpt-4o")
    prefix = ModelPricing.get_default_pricing("claude-sonnet-4-5-20250929")

    assert exact.model_id == "gpt-4o"
    assert prefix.provider == Provider.ANTHROPIC
    assert prefix.input_price_per_million == 3.0


def test_pricing_provider_fallback_when_unknown_model():
    pricing = ModelPricing.get_default_pricing("unknown-model", provider=Provider.GOOGLE)

    assert pricing.provider == Provider.GOOGLE
    assert pricing.input_price_per_million == 0.15


def test_pricing_global_default_without_provider():
    pricing = ModelPricing.get_default_pricing("totally-unknown")

    assert pricing.input_price_per_million == 2.5
    assert pricing.output_price_per_million == 10.0
