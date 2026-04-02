from ii_agent.core.config.llm_config import APITypes
from ii_agent.engine.types import Provider
from ii_agent.engine.v1.factory.factory import PROVIDER_SPEC_MAP


def test_provider_spec_map_contains_expected_bindings():
    assert PROVIDER_SPEC_MAP[APITypes.OPENAI] == Provider.OPENAI
    assert PROVIDER_SPEC_MAP[APITypes.ANTHROPIC] == Provider.ANTHROPIC
    assert PROVIDER_SPEC_MAP[APITypes.GEMINI] == Provider.GOOGLE
    assert PROVIDER_SPEC_MAP[APITypes.CUSTOM] == Provider.CUSTOM
