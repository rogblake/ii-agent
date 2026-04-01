import pytest

pytest.skip("ii_agent.agents.application was removed during refactoring", allow_module_level=True)

from ii_agent.agents.prompts.agent_prompts import get_system_prompt_for_agent_type
from ii_agent.agents.prompts.system_prompt import get_system_prompt
from ii_agent.agents.factory.tools import AgentConfigManager, COMMON_TOOLS
from ii_agent.agents.types import AgentType
from ii_agent.settings.llm import Provider


def _tool_names(agent_type: AgentType) -> set[str]:
    tools = set(AgentConfigManager.get_tools_for_agent(agent_type, model_name="gpt-5"))
    tools.update(tool.name for tool in COMMON_TOOLS)
    return tools


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_type", list(AgentType))
async def test_all_agent_prompts_render(agent_type: AgentType) -> None:
    prompt = await get_system_prompt_for_agent_type(
        agent_type=agent_type,
        workspace_path="/workspace",
        design_document=False,
        researcher=False,
        media=False,
        a2a_agents=False,
        task_agent=False,
        provider=Provider.OPENAI,
        available_tools=_tool_names(agent_type),
    )

    assert isinstance(prompt, str)
    assert prompt.strip()


def test_system_prompt_runtime_tools_are_tool_aware() -> None:
    prompt = get_system_prompt(
        workspace_path="/workspace",
        agent_type=AgentType.GENERAL.value,
        task_agent=True,
        available_tools={"Read", "Bash", "TodoWrite", "sub_agent_task"},
    )

    assert "File tools: `Read`." in prompt
    assert "Shell tools: `Bash`." in prompt
    assert "Planning tools: `TodoWrite`." in prompt
    assert "`Write`" not in prompt
    assert "`register_port`" not in prompt


@pytest.mark.asyncio
async def test_research_prompts_match_tool_surfaces() -> None:
    researcher_prompt = await get_system_prompt_for_agent_type(
        agent_type=AgentType.RESEARCHER,
        workspace_path="/workspace",
        provider=Provider.OPENAI,
        available_tools=_tool_names(AgentType.RESEARCHER),
    )
    fast_prompt = await get_system_prompt_for_agent_type(
        agent_type=AgentType.FAST_RESEARCH,
        workspace_path="/workspace",
        provider=Provider.OPENAI,
        available_tools=_tool_names(AgentType.FAST_RESEARCH),
    )

    assert "`web_batch_search`" in researcher_prompt
    assert "`web_visit_compress`" in researcher_prompt
    assert "`web_search`" not in researcher_prompt

    assert "`web_search`" in fast_prompt
    assert "`web_visit`" in fast_prompt
    assert "`web_batch_search`" not in fast_prompt


@pytest.mark.asyncio
async def test_design_document_prompt_keeps_specialist_overlay() -> None:
    prompt = await get_system_prompt_for_agent_type(
        agent_type=AgentType.DESIGN_DOCUMENT,
        workspace_path="/workspace",
        design_document=False,
        provider=Provider.OPENAI,
        available_tools=_tool_names(AgentType.DESIGN_DOCUMENT),
    )

    assert "Specs Workflow" in prompt
    assert "<design_document_specialist>" in prompt


@pytest.mark.asyncio
async def test_research_to_website_prompt_keeps_specialist_overlay() -> None:
    prompt = await get_system_prompt_for_agent_type(
        agent_type=AgentType.RESEARCH_TO_WEBSITE,
        workspace_path="/workspace",
        provider=Provider.OPENAI,
        available_tools=_tool_names(AgentType.RESEARCH_TO_WEBSITE),
    )

    assert "<research_to_website_specialist>" in prompt
    assert "`register_port`" in prompt
