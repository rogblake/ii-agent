from types import SimpleNamespace
from uuid import uuid4

import pytest

pytest.skip("ii_agent.agents.application was removed during refactoring", allow_module_level=True)

from ii_agent.core.config.llm_config import APITypes, LLMConfig
from ii_agent.agents.application.agent_service import AgentService


@pytest.mark.asyncio
async def test_create_plan_agent_adds_plan_tools(settings_factory, in_memory_storage, monkeypatch):
    fake_agent = SimpleNamespace(added=[])
    fake_agent.add_tool = lambda tool: fake_agent.added.append(tool)

    service = AgentService(config=settings_factory(), file_store=in_memory_storage)

    async def _create_agent(**kwargs):
        assert kwargs["system_prompt"]
        return fake_agent

    monkeypatch.setattr(service._agent_factory, "create_agent", _create_agent)

    session_info = SimpleNamespace(id=str(uuid4()), user_id="u1")
    llm_config = LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI)
    tool = object()
    agent = await service.create_plan_agent_v1(
        session_info=session_info,
        llm_config=llm_config,
        plan_tools=[tool],
    )

    assert agent is fake_agent
    assert fake_agent.added == [tool]
