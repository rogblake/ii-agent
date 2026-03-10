from types import SimpleNamespace
from uuid import uuid4

import pytest

from ii_agent.billing.usage.models import TokenUsage
from ii_agent.chat.application.turn_loop_service import LLMTurnLoopService
from ii_agent.chat.types import (
    EventType,
    FinishReason,
    Message,
    MessageRole,
    RunResponseEvent,
    RunResponseOutput,
    TextContent,
)
from ii_agent.core.config.llm_config import APITypes, LLMConfig


class FakeMessageService:
    def __init__(self):
        self.created = []

    async def create_message(self, db, **kwargs):
        self.created.append(kwargs)
        return Message(
            id=uuid4(),
            role=kwargs["role"],
            session_id=kwargs["session_id"],
            parts=kwargs["parts"],
            created_at=0,
            updated_at=0,
            model=kwargs.get("model_id"),
            provider=None,
            file_ids=kwargs.get("file_ids"),
            provider_metadata=kwargs.get("provider_metadata"),
            finish_reason=kwargs.get("finish_reason"),
            tokens=None,
            tools_enabled=None,
            metadata=None,
        )


class FakeProvider:
    async def stream(self, messages, tools, is_code_interpreter_enabled, session_id):
        yield RunResponseEvent(type=EventType.CONTENT_DELTA, content="partial")
        yield RunResponseEvent(
            type=EventType.COMPLETE,
            response=RunResponseOutput(
                content=[TextContent(text="done")],
                usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
                finish_reason=FinishReason.END_TURN,
                files=[],
                provider_metadata={"provider": "test"},
            ),
        )


class FakeDB:
    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_llm_turn_loop_emits_usage_and_complete(monkeypatch):
    async def _noop(*args, **kwargs):
        return None

    async def _compress_context(**kwargs):
        return kwargs["messages"]

    monkeypatch.setattr("ii_agent.chat.application.turn_loop_service.cancel.raise_if_cancelled", _noop)
    monkeypatch.setattr(
        "ii_agent.chat.application.turn_loop_service.ContextWindowManager.compress_context_if_needed",
        _compress_context,
    )
    monkeypatch.setattr(
        "ii_agent.chat.application.turn_loop_service.ContextWindowManager.check_and_summarize_after_response",
        _noop,
    )

    service = LLMTurnLoopService(message_service=FakeMessageService(), llm_billing=None)
    user_message = Message(
        id=uuid4(),
        role=MessageRole.USER,
        session_id="s1",
        parts=[TextContent(text="hello")],
        created_at=0,
        updated_at=0,
    )

    events = []
    async for event in service.run(
        FakeDB(),
        messages=[user_message],
        provider=FakeProvider(),
        tool_registry={},
        tools_to_pass=[],
        is_code_interpreter_enabled=False,
        session_id="s1",
        user_id="u1",
        model_id="gpt-4o",
        user_message=user_message,
        run_id="run-1",
        llm_config=LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI),
        chat_request=SimpleNamespace(model_id="gpt-4o"),
        tool_service=SimpleNamespace(),
    ):
        events.append(event)

    assert any(e.get("type") == "usage" for e in events)
    assert any(e.get("type") == "complete" for e in events)
