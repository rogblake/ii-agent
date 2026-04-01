from ii_agent.settings.llm import Provider


def test_provider_enum_has_expected_members():
    assert Provider.OPENAI == "OpenAI"
    assert Provider.ANTHROPIC == "Anthropic"
    assert Provider.GOOGLE == "Google"
    assert Provider.CUSTOM == "Custom"
