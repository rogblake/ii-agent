from __future__ import annotations

from types import SimpleNamespace

import pytest

from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.settings.llm import Provider


@pytest.mark.asyncio
async def test_create_agent_appends_available_skills_xml_to_system_prompt(monkeypatch):
    from ii_agent.agents.factory.agent import AgentFactory
    from ii_agent.agents.factory.tools import AgentType
    from ii_agent.agents.tools.skill import SkillTool

    captured: dict[str, object] = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def set_id(self) -> None:
            captured["set_id_called"] = True

    class FakeSkillCreator:
        async def create_skill_tool(self):
            return SkillTool(
                description=(
                    "<skills_instructions>\n"
                    "Use skills when helpful.\n"
                    "</skills_instructions>\n\n"
                    "<available_skills>\n"
                    "<skill>\n"
                    "<name>demo-skill</name>\n"
                    "<description>Demo description</description>\n"
                    "</skill>\n"
                    "</available_skills>"
                ),
                skills_registry={},
            )

    async def fake_system_prompt(**kwargs) -> str:
        return "BASE PROMPT"

    monkeypatch.setattr(
        "ii_agent.agents.factory.agent.AgentToolManager.resolve_tools",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        "ii_agent.agents.factory.agent.get_model",
        lambda provider, llm_config: SimpleNamespace(id="fake-model"),
    )
    monkeypatch.setattr(
        "ii_agent.agents.factory.agent.get_system_prompt_for_agent_type",
        fake_system_prompt,
    )
    monkeypatch.setattr("ii_agent.agents.factory.agent.IIAgent", FakeAgent)

    factory = AgentFactory(config=SimpleNamespace())
    llm_config = LLMConfig(model="gpt-4o", provider=Provider.OPENAI)

    await factory.create_agent(
        user_id="user-1",
        session_id="session-1",
        llm_config=llm_config,
        agent_type=AgentType.GENERAL,
        skill_creator=FakeSkillCreator(),
    )

    assert captured["set_id_called"] is True
    assert "<available_skills>" in captured["system_message"]
    assert "demo-skill" in captured["system_message"]
    assert captured["system_message"].startswith("BASE PROMPT")
