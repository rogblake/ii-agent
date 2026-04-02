import pytest

from ii_agent.agents.prompts.agent_prompts import get_system_prompt_for_agent_type
from ii_agent.agents.types import AgentType
from ii_agent.settings.llm import Provider


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent_type", "expected_marker"),
    [
        (AgentType.RESEARCHER, "<research_specialist>"),
        (AgentType.FAST_RESEARCH, "<research_specialist>"),
        (AgentType.DESIGN_DOCUMENT, "<design_document_specialist>"),
        (AgentType.RESEARCH_TO_WEBSITE, "<research_to_website_specialist>"),
    ],
)
async def test_specialized_agent_prompts_render(agent_type: AgentType, expected_marker: str):
    prompt = await get_system_prompt_for_agent_type(
        agent_type=agent_type,
        workspace_path="/workspace",
        provider=Provider.OPENAI,
    )

    assert expected_marker in prompt
    assert prompt.strip()
