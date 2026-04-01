"""Unit tests for factory tools configuration."""

import sys
import types

import pytest


# ---------------------------------------------------------------------------
# Patch the google.genai.interactions module BEFORE any imports that
# transitively need it.  The factory.tools -> factory.factory ->
# engine.runtime.models.google.interactions chain would otherwise fail because
# the installed google-genai version does not expose the same symbols as
# the source expects.
# ---------------------------------------------------------------------------
def _stub_google_genai_interactions():
    """Replace google.genai.interactions with a stub that satisfies the import."""
    symbols = [
        "InteractionSSEEvent",
        "InteractionEvent",
        "ContentStart",
        "ContentDelta",
        "Usage",
        "ContentStop",
        "Interaction",
        "InputMessage",
        "OutputMessage",
        "InteractionResultEvent",
        "FunctionCallInteractionResultEvent",
        "ContentInteractionResultEvent",
    ]
    mod = types.ModuleType("google.genai.interactions")
    for sym in symbols:
        setattr(mod, sym, type(sym, (), {}))
    sys.modules["google.genai.interactions"] = mod
    # Do NOT stub _interactions - it loads fine from the installed package


_stub_google_genai_interactions()

# Now the factory can be imported.
from ii_agent.agents.factory.tools import (  # noqa: E402
    AgentConfigManager,
    AgentToolConfig,
    AgentConfig,
    AGENT_CONFIGS,
    TOOL_CLASS_MAP,
    TOOL_CONFIRM_MAP,
    COMMON_TOOLS,
)
from ii_agent.agents.types import AgentType  # noqa: E402
from ii_agent.settings.llm import Provider  # noqa: E402


# ---------------------------------------------------------------------------
# AgentToolConfig dataclass tests
# ---------------------------------------------------------------------------


class TestAgentToolConfig:
    def test_minimal_config(self):
        config = AgentToolConfig(core_tools=["tool_a", "tool_b"])
        assert config.core_tools == ["tool_a", "tool_b"]
        assert config.model_exclusions is None
        assert config.model_additions is None

    def test_config_with_exclusions(self):
        config = AgentToolConfig(
            core_tools=["tool_a"],
            model_exclusions={Provider.OPENAI: ["tool_a"]},
        )
        assert Provider.OPENAI in config.model_exclusions
        assert "tool_a" in config.model_exclusions[Provider.OPENAI]

    def test_config_with_additions(self):
        config = AgentToolConfig(
            core_tools=["tool_a"],
            model_additions={Provider.ANTHROPIC: ["tool_b"]},
        )
        assert Provider.ANTHROPIC in config.model_additions

    def test_config_core_tools_order_preserved(self):
        tools = ["z_tool", "a_tool", "m_tool"]
        config = AgentToolConfig(core_tools=tools)
        assert config.core_tools == tools

    def test_empty_core_tools(self):
        config = AgentToolConfig(core_tools=[])
        assert config.core_tools == []

    def test_both_exclusions_and_additions(self):
        config = AgentToolConfig(
            core_tools=["tool_a", "tool_b"],
            model_exclusions={Provider.OPENAI: ["tool_b"]},
            model_additions={Provider.OPENAI: ["tool_c"]},
        )
        assert "tool_b" in config.model_exclusions[Provider.OPENAI]
        assert "tool_c" in config.model_additions[Provider.OPENAI]


# ---------------------------------------------------------------------------
# AgentConfig dataclass tests
# ---------------------------------------------------------------------------


class TestAgentConfig:
    def test_defaults(self):
        tool_config = AgentToolConfig(core_tools=[])
        config = AgentConfig(
            agent_type=AgentType.GENERAL,
            description="Test agent",
            tool_config=tool_config,
        )
        assert config.max_turns == 200
        assert config.supports_media is False
        assert config.supports_design_doc is False

    def test_custom_values(self):
        tool_config = AgentToolConfig(core_tools=[])
        config = AgentConfig(
            agent_type=AgentType.GENERAL,
            description="Test agent",
            tool_config=tool_config,
            max_turns=50,
            supports_media=True,
            supports_design_doc=True,
        )
        assert config.max_turns == 50
        assert config.supports_media is True
        assert config.supports_design_doc is True

    def test_description_stored(self):
        tc = AgentToolConfig(core_tools=[])
        config = AgentConfig(
            agent_type=AgentType.RESEARCHER,
            description="Research agent for gathering info",
            tool_config=tc,
        )
        assert config.description == "Research agent for gathering info"

    def test_agent_type_stored(self):
        tc = AgentToolConfig(core_tools=[])
        config = AgentConfig(
            agent_type=AgentType.MEDIA,
            description="Media agent",
            tool_config=tc,
        )
        assert config.agent_type == AgentType.MEDIA


# ---------------------------------------------------------------------------
# AgentConfigManager.get_config tests
# ---------------------------------------------------------------------------


class TestGetConfig:
    def test_get_config_general(self):
        config = AgentConfigManager.get_config(AgentType.GENERAL)
        assert config.agent_type == AgentType.GENERAL

    def test_get_config_researcher(self):
        config = AgentConfigManager.get_config(AgentType.RESEARCHER)
        assert config.agent_type == AgentType.RESEARCHER

    def test_get_config_media(self):
        config = AgentConfigManager.get_config(AgentType.MEDIA)
        assert config.agent_type == AgentType.MEDIA

    def test_get_config_slide(self):
        config = AgentConfigManager.get_config(AgentType.SLIDE)
        assert config.agent_type == AgentType.SLIDE

    def test_get_config_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown agent type"):
            AgentConfigManager.get_config("unknown_type")

    def test_all_registered_agent_types_retrievable(self):
        for agent_type in AgentType:
            if agent_type in AGENT_CONFIGS:
                config = AgentConfigManager.get_config(agent_type)
                assert config.agent_type == agent_type

    def test_returns_agent_config_instance(self):
        config = AgentConfigManager.get_config(AgentType.SLIDE)
        assert isinstance(config, AgentConfig)


# ---------------------------------------------------------------------------
# AgentConfigManager._get_model_family tests
# ---------------------------------------------------------------------------


class TestGetModelFamily:
    def test_gpt_model_returns_openai(self):
        result = AgentConfigManager._get_model_family("gpt-4o")
        assert result == Provider.OPENAI

    def test_gpt4_model_returns_openai(self):
        result = AgentConfigManager._get_model_family("gpt-4-turbo")
        assert result == Provider.OPENAI

    def test_claude_model_returns_anthropic(self):
        result = AgentConfigManager._get_model_family("claude-opus-4")
        assert result == Provider.ANTHROPIC

    def test_claude_3_model_returns_anthropic(self):
        result = AgentConfigManager._get_model_family("claude-3-sonnet-20240229")
        assert result == Provider.ANTHROPIC

    def test_gemini_model_returns_google(self):
        result = AgentConfigManager._get_model_family("gemini-1.5-pro")
        assert result == Provider.GOOGLE

    def test_vertex_model_returns_vertex_ai(self):
        # "vertex" without other provider keywords in the name
        result = AgentConfigManager._get_model_family("vertex-custom-model")
        assert result == Provider.VERTEX_AI

    def test_azure_model_returns_azure(self):
        # "azure" without other provider keywords in the name
        result = AgentConfigManager._get_model_family("azure-custom-model")
        assert result == Provider.AZURE

    def test_cerebras_model_returns_cerebras(self):
        result = AgentConfigManager._get_model_family("cerebras-llama")
        assert result == Provider.CEREBRAS

    def test_unknown_model_returns_none(self):
        result = AgentConfigManager._get_model_family("totally-unknown-model")
        assert result is None

    def test_o3_model_returns_openai(self):
        result = AgentConfigManager._get_model_family("o3-mini")
        assert result == Provider.OPENAI

    def test_openai_in_name_returns_openai(self):
        result = AgentConfigManager._get_model_family("openai-custom")
        assert result == Provider.OPENAI

    def test_anthropic_in_name_returns_anthropic(self):
        result = AgentConfigManager._get_model_family("anthropic-custom")
        assert result == Provider.ANTHROPIC

    def test_case_insensitive_detection(self):
        assert AgentConfigManager._get_model_family("GPT-4") == Provider.OPENAI
        assert AgentConfigManager._get_model_family("CLAUDE-3") == Provider.ANTHROPIC
        assert AgentConfigManager._get_model_family("GEMINI-PRO") == Provider.GOOGLE


# ---------------------------------------------------------------------------
# AgentConfigManager.get_tools_for_agent tests
# ---------------------------------------------------------------------------


class TestGetToolsForAgent:
    def test_returns_core_tools_for_general_agent(self):
        tools = AgentConfigManager.get_tools_for_agent(AgentType.GENERAL)
        assert len(tools) > 0

    def test_returns_set_of_strings(self):
        tools = AgentConfigManager.get_tools_for_agent(AgentType.GENERAL)
        assert isinstance(tools, set)
        assert all(isinstance(t, str) for t in tools)

    def test_applies_openai_model_exclusions(self):
        tools_with_openai = AgentConfigManager.get_tools_for_agent(
            AgentType.GENERAL, model_name="gpt-4o"
        )
        config = AgentConfigManager.get_config(AgentType.GENERAL)
        openai_exclusions = config.tool_config.model_exclusions.get(Provider.OPENAI, [])
        for excluded_tool in openai_exclusions:
            assert excluded_tool not in tools_with_openai

    def test_applies_anthropic_model_additions(self):
        tools = AgentConfigManager.get_tools_for_agent(
            AgentType.GENERAL, model_name="claude-opus-4"
        )
        config = AgentConfigManager.get_config(AgentType.GENERAL)
        anthropic_additions = config.tool_config.model_additions.get(Provider.ANTHROPIC, [])
        for added_tool in anthropic_additions:
            assert added_tool in tools

    def test_applies_openai_model_additions(self):
        tools = AgentConfigManager.get_tools_for_agent(AgentType.GENERAL, model_name="gpt-4o")
        config = AgentConfigManager.get_config(AgentType.GENERAL)
        openai_additions = config.tool_config.model_additions.get(Provider.OPENAI, [])
        for added_tool in openai_additions:
            assert added_tool in tools

    def test_does_not_add_media_when_agent_does_not_support_it(self):
        initial_tools = AgentConfigManager.get_tools_for_agent(AgentType.RESEARCHER)
        tools_with_media = AgentConfigManager.get_tools_for_agent(
            AgentType.RESEARCHER, tool_args={"media_generation": True}
        )
        config = AgentConfigManager.get_config(AgentType.RESEARCHER)
        assert config.supports_media is False
        assert initial_tools == tools_with_media

    def test_default_tool_args_as_none(self):
        tools = AgentConfigManager.get_tools_for_agent(AgentType.GENERAL, tool_args=None)
        assert len(tools) > 0

    def test_unknown_model_has_no_exclusions_or_additions(self):
        tools_no_model = AgentConfigManager.get_tools_for_agent(AgentType.GENERAL)
        tools_unknown = AgentConfigManager.get_tools_for_agent(
            AgentType.GENERAL, model_name="some-totally-unknown-provider"
        )
        assert tools_no_model == tools_unknown

    def test_media_tools_added_for_supported_agent_with_flag(self):
        tools = AgentConfigManager.get_tools_for_agent(
            AgentType.GENERAL, tool_args={"media_generation": True}
        )
        config = AgentConfigManager.get_config(AgentType.GENERAL)
        assert config.supports_media is True
        from ii_agent.agents.tools.media import ImageGenerateTool

        assert ImageGenerateTool.name in tools


# ---------------------------------------------------------------------------
# AgentConfigManager.is_valid_agent_type tests
# ---------------------------------------------------------------------------


class TestIsValidAgentType:
    def test_valid_agent_type(self):
        assert AgentConfigManager.is_valid_agent_type("general") is True

    def test_invalid_agent_type(self):
        assert AgentConfigManager.is_valid_agent_type("not_a_real_type") is False

    def test_researcher_is_valid(self):
        assert AgentConfigManager.is_valid_agent_type("researcher") is True

    def test_empty_string_invalid(self):
        assert AgentConfigManager.is_valid_agent_type("") is False


class TestGetAllAgentTypes:
    def test_returns_list_of_strings(self):
        types = AgentConfigManager.get_all_agent_types()
        assert isinstance(types, list)
        assert all(isinstance(t, str) for t in types)

    def test_includes_general_type(self):
        types = AgentConfigManager.get_all_agent_types()
        assert "general" in types

    def test_includes_researcher_type(self):
        types = AgentConfigManager.get_all_agent_types()
        assert "researcher" in types

    def test_returns_all_agent_type_enum_values(self):
        all_types = AgentConfigManager.get_all_agent_types()
        for at in AgentType:
            assert at.value in all_types


# ---------------------------------------------------------------------------
# Global config constants tests
# ---------------------------------------------------------------------------


class TestGlobalConfigConstants:
    def test_tool_class_map_not_empty(self):
        assert len(TOOL_CLASS_MAP) > 0

    def test_tool_class_map_values_are_classes(self):
        import inspect

        for name, cls in TOOL_CLASS_MAP.items():
            assert inspect.isclass(cls), f"{name} should map to a class"

    def test_tool_class_map_keys_match_tool_names(self):
        for name, cls in TOOL_CLASS_MAP.items():
            assert cls.name == name, f"Key {name!r} should match {cls}.name={cls.name!r}"

    def test_common_tools_is_a_set(self):
        assert isinstance(COMMON_TOOLS, set)

    def test_tool_confirm_map_is_dict(self):
        assert isinstance(TOOL_CONFIRM_MAP, dict)

    def test_agent_configs_covers_main_types(self):
        assert AgentType.GENERAL in AGENT_CONFIGS
        assert AgentType.RESEARCHER in AGENT_CONFIGS
        assert AgentType.MEDIA in AGENT_CONFIGS
        assert AgentType.SLIDE in AGENT_CONFIGS

    def test_general_agent_supports_media(self):
        config = AGENT_CONFIGS[AgentType.GENERAL]
        assert config.supports_media is True

    def test_researcher_agent_minimal_tools(self):
        config = AGENT_CONFIGS[AgentType.RESEARCHER]
        assert len(config.tool_config.core_tools) > 0

    def test_all_agent_configs_have_descriptions(self):
        for agent_type, config in AGENT_CONFIGS.items():
            assert config.description, f"{agent_type} config should have a description"
