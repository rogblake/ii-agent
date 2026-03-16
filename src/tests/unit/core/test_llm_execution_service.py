from types import SimpleNamespace
from uuid import uuid4
from decimal import Decimal

import pytest

from ii_agent.billing.usage.models import TokenUsage
from ii_agent.chat.types import (
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


class FakeReservedLLMCall:
    """Minimal fake matching the ReservedLLMCall shape."""

    def __init__(self, provider_options=None):
        self.hold = SimpleNamespace(reservation_id="res-1")
        self.input_tokens_estimate = 100
        self.output_token_cap = 4096
        self.pricing = None
        self.provider_options = provider_options


class FakeBillingService:
    def __init__(self, *, reservation=None, settle_result=None):
        self.reserve_calls = []
        self.settle_calls = []
        self.release_calls = []
        self.mark_failed_calls = []
        self._reservation = reservation
        self._settle_result = settle_result

    async def reserve_chat_llm_call(self, db, **kwargs):
        self.reserve_calls.append(kwargs)
        return self._reservation

    async def settle_chat_llm_call(self, db, **kwargs):
        self.settle_calls.append(kwargs)
        return self._settle_result

    async def release_llm_call(self, db, *, reservation, reason):
        self.release_calls.append(SimpleNamespace(reservation=reservation, reason=reason))
        return None

    async def mark_settlement_failed(self, db, *, reservation_id, error):
        self.mark_failed_calls.append(
            SimpleNamespace(reservation_id=reservation_id, error=error)
        )


class FakeInvocationRepo:
    def __init__(self):
        self.calls = []

    async def create(self, db, **kwargs):
        self.calls.append(SimpleNamespace(db=db, **kwargs))
        return self.calls[-1]


class FailingInvocationRepo:
    async def create(self, db, **kwargs):
        raise RuntimeError("telemetry failed")


class FakeNestedTransaction:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        self._db.begin_nested_calls += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeDB:
    def __init__(self):
        self.begin_nested_calls = 0

    def begin_nested(self):
        return FakeNestedTransaction(self)


class FakeClient:
    def __init__(self, responses):
        self._responses = responses
        self.calls = 0
        self.provider_options = []

    async def send(self, messages, tools=None, provider_options=None):
        self.provider_options.append(provider_options)
        response = self._responses[self.calls]
        self.calls += 1
        return response


def _billing_context(llm_config: LLMConfig) -> LLMBillingContext:
    return LLMBillingContext(
        db=FakeDB(),
        user_id="u1",
        session_id="s1",
        llm_config=llm_config,
        model_id=llm_config.model,
    )


@pytest.mark.asyncio
async def test_send_once_reserves_settles_on_success():
    """send_once should reserve before call and settle after."""
    llm_config = LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI, config_type="system")
    settle_result = SimpleNamespace(total_charged=Decimal("0.1"))
    reservation = FakeReservedLLMCall()
    billing = FakeBillingService(reservation=reservation, settle_result=settle_result)
    invocation_repo = FakeInvocationRepo()
    service = LLMExecutionService(
        llm_billing=billing,
        llm_invocation_repo=invocation_repo,
    )
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
        usage_key="test_reserve_settle",
    )

    assert response.finish_reason == FinishReason.END_TURN
    assert len(billing.reserve_calls) == 1
    assert len(billing.settle_calls) == 1
    assert len(billing.release_calls) == 0
    assert billing.reserve_calls[0]["user_id"] == "u1"
    assert billing.reserve_calls[0]["session_id"] == "s1"
    assert len(invocation_repo.calls) == 1
    assert invocation_repo.calls[0].finish_reason == "end_turn"


@pytest.mark.asyncio
async def test_send_once_skips_billing_for_user_model():
    """User-provided models should not trigger reservation."""
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
        usage_key="test_user_model",
    )

    assert len(billing.reserve_calls) == 0
    assert len(billing.settle_calls) == 0


@pytest.mark.asyncio
async def test_send_once_uses_reservation_provider_options():
    """Provider options from reservation should be forwarded to client."""
    llm_config = LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI, config_type="system")
    reservation = FakeReservedLLMCall(
        provider_options={"openai": {"max_output_tokens": 4096}}
    )
    billing = FakeBillingService(reservation=reservation)
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
        parts=[TextContent(text="hello")],
        created_at=0,
        updated_at=0,
    )

    await service.send_once(
        client=client,
        messages=[message],
        billing_context=_billing_context(llm_config),
        usage_key="test_provider_options",
    )

    assert client.provider_options == [{"openai": {"max_output_tokens": 4096}}]


@pytest.mark.asyncio
async def test_send_once_releases_reservation_on_error():
    """Provider failure should release the reservation, not settle."""
    llm_config = LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI, config_type="system")
    reservation = FakeReservedLLMCall()
    billing = FakeBillingService(reservation=reservation)
    invocation_repo = FakeInvocationRepo()
    service = LLMExecutionService(
        llm_billing=billing,
        llm_invocation_repo=invocation_repo,
    )

    class FailingClient:
        async def send(self, messages, tools=None, provider_options=None):
            raise RuntimeError("provider failed")

    message = Message(
        id=uuid4(),
        role=MessageRole.USER,
        session_id="s1",
        parts=[TextContent(text="hello")],
        created_at=0,
        updated_at=0,
    )

    with pytest.raises(RuntimeError, match="provider failed"):
        await service.send_once(
            client=FailingClient(),
            messages=[message],
            billing_context=_billing_context(llm_config),
            usage_key="test_release_on_error",
        )

    assert len(billing.reserve_calls) == 1
    assert len(billing.release_calls) == 1
    assert billing.release_calls[0].reason == "provider_error"
    assert len(billing.settle_calls) == 0
    assert len(invocation_repo.calls) == 1
    assert invocation_repo.calls[0].success is False


@pytest.mark.asyncio
async def test_tool_loop_reserves_and_settles_each_step(monkeypatch):
    """Each tool-loop step should get its own reserve/settle cycle."""
    llm_config = LLMConfig(model="claude-4-5-sonnet", config_type="system")
    reservation = FakeReservedLLMCall()
    settle_result = SimpleNamespace(total_charged=Decimal("0.05"))
    billing = FakeBillingService(reservation=reservation, settle_result=settle_result)
    invocation_repo = FakeInvocationRepo()
    service = LLMExecutionService(
        llm_billing=billing,
        llm_invocation_repo=invocation_repo,
    )

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
        usage_key_prefix="test_tool_loop",
    )

    assert result.final_payload == {"operations": [{"op": "set_text"}]}
    assert executed_tools == [("call-1", "search_tool", '{"query":"button"}')]
    # Two LLM calls → two reserves, two settles
    assert len(billing.reserve_calls) == 2
    assert len(billing.settle_calls) == 2
    assert len(billing.release_calls) == 0
    request_kinds = [call.request_kind for call in invocation_repo.calls]
    assert len(request_kinds) == 2
    assert request_kinds[0] == "test_tool_loop:step_0"
    assert request_kinds[1] == "test_tool_loop:step_1"


@pytest.mark.asyncio
async def test_send_once_ignores_telemetry_write_failures():
    """Invocation repo failures should not block execution."""
    llm_config = LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI, config_type="system")
    billing = FakeBillingService(reservation=FakeReservedLLMCall())
    service = LLMExecutionService(
        llm_billing=billing,
        llm_invocation_repo=FailingInvocationRepo(),
    )
    client = FakeClient(
        [
            RunResponseOutput(
                content=[TextContent(text="done")],
                usage=TokenUsage(prompt_tokens=2, completion_tokens=1),
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
        usage_key="test_telemetry_failure",
    )

    assert response.finish_reason == FinishReason.END_TURN
    assert len(billing.reserve_calls) == 1
    assert len(billing.settle_calls) == 1


@pytest.mark.asyncio
async def test_send_once_no_billing_without_context():
    """No billing_context means no reservation work."""
    service = LLMExecutionService()
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
        parts=[TextContent(text="hello")],
        created_at=0,
        updated_at=0,
    )

    response = await service.send_once(
        client=client,
        messages=[message],
    )

    assert response.finish_reason == FinishReason.END_TURN
