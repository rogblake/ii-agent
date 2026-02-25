from types import SimpleNamespace
from uuid import uuid4

import pytest

from ii_agent.billing.usage.models import TokenUsage
from ii_agent.chat.schemas import (
    FinishReason,
    Message,
    MessageRole,
    RunResponseOutput,
    TextContent,
    TextResultContent,
    ToolCall,
    ToolResult,
)
from ii_agent.core.config.llm_config import APITypes, LLMConfig
from ii_agent.core.llm.execution_service import LLMExecutionService, LLMBillingContext


class FakeBillingService:
    def __init__(self):
        self.calls = []

    async def deduct_for_llm_usage(
        self,
        db,
        *,
        user_id: str,
        session_id: str,
        token_record,
        is_user_model: bool = False,
    ):
        self.calls.append(
            SimpleNamespace(
                db=db,
                user_id=user_id,
                session_id=session_id,
                token_record=token_record,
                is_user_model=is_user_model,
            )
        )
        return 0.1


class FakeClient:
    def __init__(self, responses):
        self._responses = responses
        self.calls = 0

    async def send(self, messages, tools=None):
        response = self._responses[self.calls]
        self.calls += 1
        return response


def _billing_context(llm_config: LLMConfig) -> LLMBillingContext:
    return LLMBillingContext(
        db=SimpleNamespace(),
        user_id="u1",
        session_id="s1",
        llm_config=llm_config,
        model_id=llm_config.model,
    )


@pytest.mark.asyncio
async def test_send_once_bills_with_model_fallback():
    llm_config = LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI, config_type="system")
    billing = FakeBillingService()
    service = LLMExecutionService(llm_billing=billing)
    client = FakeClient(
        [
            RunResponseOutput(
                content=[TextContent(text="enhanced prompt")],
                usage=TokenUsage(prompt_tokens=10, completion_tokens=6),
                finish_reason=FinishReason.END_TURN,
            )
        ]
    )
    message = Message(
        id=uuid4(),
        role=MessageRole.USER,
        session_id="s1",
        parts=[TextContent(text="hello")],
        created_at=0,
        updated_at=0,
    )

    response = await service.send_once(
        client=client,
        messages=[message],
        billing_context=_billing_context(llm_config),
    )

    assert response.finish_reason == FinishReason.END_TURN
    assert len(billing.calls) == 1
    assert billing.calls[0].token_record.model_id == "gpt-4o"
    assert billing.calls[0].session_id == "s1"


@pytest.mark.asyncio
async def test_send_once_passes_user_model_flag():
    llm_config = LLMConfig(
        model="gpt-4o",
        api_type=APITypes.OPENAI,
        config_type="user",
    )
    billing = FakeBillingService()
    service = LLMExecutionService(llm_billing=billing)
    client = FakeClient(
        [
            RunResponseOutput(
                content=[TextContent(text="done")],
                usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
                finish_reason=FinishReason.END_TURN,
            )
        ]
    )
    message = Message(
        id=uuid4(),
        role=MessageRole.USER,
        session_id="s1",
        parts=[TextContent(text="x")],
        created_at=0,
        updated_at=0,
    )

    await service.send_once(
        client=client,
        messages=[message],
        billing_context=_billing_context(llm_config),
    )

    assert len(billing.calls) == 1
    assert billing.calls[0].is_user_model is True


@pytest.mark.asyncio
async def test_tool_loop_returns_final_payload_and_bills_each_step(monkeypatch):
    llm_config = LLMConfig(model="claude-4-5-sonnet", config_type="system")
    billing = FakeBillingService()
    service = LLMExecutionService(llm_billing=billing)

    client = FakeClient(
        [
            RunResponseOutput(
                content=[
                    ToolCall(
                        id="call-1",
                        name="search_tool",
                        input='{"query":"button"}',
                    )
                ],
                usage=TokenUsage(prompt_tokens=11, completion_tokens=4),
                finish_reason=FinishReason.TOOL_USE,
            ),
            RunResponseOutput(
                content=[
                    ToolCall(
                        id="call-2",
                        name="final_tool",
                        input='{"operations":[{"op":"set_text"}]}',
                    )
                ],
                usage=TokenUsage(prompt_tokens=7, completion_tokens=3),
                finish_reason=FinishReason.TOOL_USE,
            ),
        ]
    )

    executed_tools = []

    async def _fake_execute_tool(*, tool_call_id, tool_name, tool_input, tool_registry):
        executed_tools.append((tool_call_id, tool_name, tool_input))
        return ToolResult(
            tool_call_id=tool_call_id,
            name=tool_name,
            output=TextResultContent(value="ok"),
        )

    monkeypatch.setattr(
        "ii_agent.core.llm.execution_service.ChatToolService.execute_tool",
        _fake_execute_tool,
    )

    user_message = Message(
        id=uuid4(),
        role=MessageRole.USER,
        session_id="s1",
        parts=[TextContent(text="make it cleaner")],
        created_at=0,
        updated_at=0,
    )

    result = await service.run_tool_loop_until_final(
        client=client,
        session_id="s1",
        messages=[user_message],
        tools=[],
        final_tool_name="final_tool",
        tool_registry={"search_tool": object(), "final_tool": object()},
        max_loops=4,
        billing_context=_billing_context(llm_config),
    )

    assert result.final_payload == {"operations": [{"op": "set_text"}]}
    assert executed_tools == [("call-1", "search_tool", '{"query":"button"}')]
    assert len(billing.calls) == 2
