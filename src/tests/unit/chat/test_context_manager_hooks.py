from uuid import uuid4

import pytest

from ii_agent.chat.context_manager import ContextWindowManager
from ii_agent.chat.schemas import Message, MessageRole, TextContent
from ii_agent.core.config.llm_config import APITypes, LLMConfig


@pytest.mark.asyncio
async def test_compress_context_if_needed_noop_below_threshold():
    messages = [
        Message(
            id=uuid4(),
            role=MessageRole.USER,
            session_id="s1",
            parts=[TextContent(text="hello")],
            tokens=10,
            created_at=0,
            updated_at=0,
        )
    ]

    llm_config = LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI)

    result = await ContextWindowManager.compress_context_if_needed(
        db_session=None,
        messages=messages,
        session_id="s1",
        llm_config=llm_config,
        user_id="u1",
    )

    assert result is messages
