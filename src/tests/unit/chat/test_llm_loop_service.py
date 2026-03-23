from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ii_agent.billing.exceptions import BillingSettlementFinalError
from ii_agent.billing.types import BillingContextValue
from ii_agent.billing.reservations.types import BillingQuote
from ii_agent.billing.usage.models import TokenUsage
from ii_agent.chat.application.turn_loop_service import LLMTurnLoopService
from ii_agent.chat.tools.base import ToolResponse
from ii_agent.chat.types import (
    EventType,
    FinishReason,
    Message,
    MessageRole,
    RunResponseEvent,
    RunResponseOutput,
    StorybookProgressContent,
    TextContent,
    TextResultContent,
    ToolCall,
    ToolResult,
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
    async def stream(
        self,
        messages,
        tools,
        is_code_interpreter_enabled,
        session_id,
        provider_options=None,
    ):
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


class FakeToolUseProvider:
    def __init__(self):
        self.calls = 0

    async def stream(
        self,
        messages,
        tools,
        is_code_interpreter_enabled,
        session_id,
        provider_options=None,
    ):
        if self.calls == 0:
            self.calls += 1
            yield RunResponseEvent(
                type=EventType.COMPLETE,
                response=RunResponseOutput(
                    content=[
                        ToolCall(
                            id="call-1",
                            name="search_tool",
                            input='{"query":"hello"}',
                        )
                    ],
                    usage=TokenUsage(prompt_tokens=12, completion_tokens=4),
                    finish_reason=FinishReason.TOOL_USE,
                    files=[],
                    provider_metadata={"provider": "test"},
                ),
            )
            return

        self.calls += 1
        yield RunResponseEvent(
            type=EventType.COMPLETE,
            response=RunResponseOutput(
                content=[TextContent(text="done")],
                usage=TokenUsage(prompt_tokens=6, completion_tokens=2),
                finish_reason=FinishReason.END_TURN,
                files=[],
                provider_metadata={"provider": "test"},
            ),
        )


class FakeInvocationRepo:
    def __init__(self):
        self.calls = []

    async def create(self, db, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(**kwargs)


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
        self.commit_calls = 0

    def begin_nested(self):
        return FakeNestedTransaction(self)

    async def commit(self):
        self.commit_calls += 1
        return None


class FailingProvider:
    async def stream(
        self,
        messages,
        tools,
        is_code_interpreter_enabled,
        session_id,
        provider_options=None,
    ):
        if False:
            yield None
        raise RuntimeError("provider failed")


class FakeStorybookTool:
    supports_streaming = True
    name = "generate_storybook"

    async def quote_cost(self, tool_call):
        return BillingQuote(strategy="bounded", reserve_usd=0.5, max_usd=0.5)

    async def start_celery_generation(self, *args, **kwargs):
        return ToolResponse(
            output=StorybookProgressContent(
                storybook_id="sb-1",
                storybook_name="Story",
                total_pages=3,
                completed_pages=0,
                current_page=1,
                status="generating",
                pages=[],
                generating_pages=[1],
                polling=True,
            )
        )


class FakeStorybookProvider:
    async def stream(
        self, messages, tools, is_code_interpreter_enabled, session_id, provider_options=None
    ):
        yield RunResponseEvent(
            type=EventType.COMPLETE,
            response=RunResponseOutput(
                content=[
                    ToolCall(
                        id="call-1",
                        name="generate_storybook",
                        input='{"title":"Story","scenes":[{"text":"page"}]}',
                    )
                ],
                usage=TokenUsage(prompt_tokens=12, completion_tokens=4),
                finish_reason=FinishReason.TOOL_USE,
                files=[],
                provider_metadata={"provider": "test"},
            ),
        )


@pytest.mark.asyncio
async def test_llm_turn_loop_emits_usage_and_complete(monkeypatch):
    async def _noop(*args, **kwargs):
        return None

    async def _compress_context(**kwargs):
        return kwargs["messages"]

    monkeypatch.setattr(
        "ii_agent.chat.application.turn_loop_service.cancel.raise_if_cancelled", _noop
    )
    monkeypatch.setattr(
        "ii_agent.chat.application.turn_loop_service.ContextWindowManager.compress_context_if_needed",
        _compress_context,
    )
    monkeypatch.setattr(
        "ii_agent.chat.application.turn_loop_service.ContextWindowManager.check_and_summarize_after_response",
        _noop,
    )

    llm_invocation_repo = FakeInvocationRepo()
    service = LLMTurnLoopService(
        message_service=FakeMessageService(),
        llm_billing=None,
        llm_invocation_repo=llm_invocation_repo,
    )
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
    assert len(llm_invocation_repo.calls) == 1
    assert llm_invocation_repo.calls[0]["request_kind"] == "chat_response"


@pytest.mark.asyncio
async def test_llm_turn_loop_records_tool_and_llm_invocations(monkeypatch):
    async def _noop(*args, **kwargs):
        return None

    async def _compress_context(**kwargs):
        return kwargs["messages"]

    async def _execute_tool(**kwargs):
        return ToolResult(
            tool_call_id=kwargs["tool_call_id"],
            name=kwargs["tool_name"],
            output=TextResultContent(value="ok"),
        )

    monkeypatch.setattr(
        "ii_agent.chat.application.turn_loop_service.cancel.raise_if_cancelled",
        _noop,
    )
    monkeypatch.setattr(
        "ii_agent.chat.application.turn_loop_service.ContextWindowManager.compress_context_if_needed",
        _compress_context,
    )
    monkeypatch.setattr(
        "ii_agent.chat.application.turn_loop_service.ContextWindowManager.check_and_summarize_after_response",
        _noop,
    )

    llm_invocation_repo = FakeInvocationRepo()
    tool_invocation_repo = FakeInvocationRepo()
    service = LLMTurnLoopService(
        message_service=FakeMessageService(),
        llm_billing=None,
        llm_invocation_repo=llm_invocation_repo,
        tool_invocation_repo=tool_invocation_repo,
    )
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
        provider=FakeToolUseProvider(),
        tool_registry={"search_tool": object()},
        tools_to_pass=[],
        is_code_interpreter_enabled=False,
        session_id="s1",
        user_id="u1",
        model_id="gpt-4o",
        user_message=user_message,
        run_id=str(uuid4()),
        llm_config=LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI),
        chat_request=SimpleNamespace(model_id="gpt-4o"),
        tool_service=SimpleNamespace(execute_tool=_execute_tool),
    ):
        events.append(event)

    assert any(e.get("type") == "tool_result" for e in events)
    assert any(e.get("type") == "complete" for e in events)
    assert [call["request_kind"] for call in llm_invocation_repo.calls] == [
        "chat_tool_use",
        "chat_response",
    ]
    assert len(tool_invocation_repo.calls) == 1
    assert tool_invocation_repo.calls[0]["tool_name"] == "search_tool"
    assert tool_invocation_repo.calls[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_llm_turn_loop_ignores_telemetry_write_failures(monkeypatch):
    async def _noop(*args, **kwargs):
        return None

    async def _compress_context(**kwargs):
        return kwargs["messages"]

    async def _execute_tool(**kwargs):
        return ToolResult(
            tool_call_id=kwargs["tool_call_id"],
            name=kwargs["tool_name"],
            output=TextResultContent(value="ok"),
        )

    monkeypatch.setattr(
        "ii_agent.chat.application.turn_loop_service.cancel.raise_if_cancelled",
        _noop,
    )
    monkeypatch.setattr(
        "ii_agent.chat.application.turn_loop_service.ContextWindowManager.compress_context_if_needed",
        _compress_context,
    )
    monkeypatch.setattr(
        "ii_agent.chat.application.turn_loop_service.ContextWindowManager.check_and_summarize_after_response",
        _noop,
    )

    db = FakeDB()
    service = LLMTurnLoopService(
        message_service=FakeMessageService(),
        llm_billing=None,
        llm_invocation_repo=FailingInvocationRepo(),
        tool_invocation_repo=FailingInvocationRepo(),
    )
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
        db,
        messages=[user_message],
        provider=FakeToolUseProvider(),
        tool_registry={"search_tool": object()},
        tools_to_pass=[],
        is_code_interpreter_enabled=False,
        session_id="s1",
        user_id="u1",
        model_id="gpt-4o",
        user_message=user_message,
        run_id=str(uuid4()),
        llm_config=LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI),
        chat_request=SimpleNamespace(model_id="gpt-4o"),
        tool_service=SimpleNamespace(execute_tool=_execute_tool),
    ):
        events.append(event)

    assert any(e.get("type") == "complete" for e in events)
    assert db.commit_calls == 2
    assert db.begin_nested_calls >= 3


@pytest.mark.asyncio
async def test_llm_turn_loop_records_failed_invocation_on_provider_error(monkeypatch):
    async def _noop(*args, **kwargs):
        return None

    async def _compress_context(**kwargs):
        return kwargs["messages"]

    monkeypatch.setattr(
        "ii_agent.chat.application.turn_loop_service.cancel.raise_if_cancelled",
        _noop,
    )
    monkeypatch.setattr(
        "ii_agent.chat.application.turn_loop_service.ContextWindowManager.compress_context_if_needed",
        _compress_context,
    )

    llm_invocation_repo = FakeInvocationRepo()
    service = LLMTurnLoopService(
        message_service=FakeMessageService(),
        llm_billing=None,
        llm_invocation_repo=llm_invocation_repo,
    )
    user_message = Message(
        id=uuid4(),
        role=MessageRole.USER,
        session_id="s1",
        parts=[TextContent(text="hello")],
        created_at=0,
        updated_at=0,
    )

    with pytest.raises(RuntimeError, match="provider failed"):
        async for _ in service.run(
            FakeDB(),
            messages=[user_message],
            provider=FailingProvider(),
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
            pass

    assert len(llm_invocation_repo.calls) == 1
    assert llm_invocation_repo.calls[0]["request_kind"] == "chat_response"
    assert llm_invocation_repo.calls[0]["success"] is False
    assert llm_invocation_repo.calls[0]["error_code"] == "runtime"


@pytest.mark.asyncio
async def test_settle_chat_llm_billing_leaves_hold_on_settlement_failure(monkeypatch):
    @asynccontextmanager
    async def _db_cm():
        yield object()

    billing = SimpleNamespace(
        settle_llm_call=AsyncMock(side_effect=RuntimeError("boom")),
        mark_settlement_failed=AsyncMock(),
    )
    service = LLMTurnLoopService(message_service=FakeMessageService(), llm_billing=billing)
    release = AsyncMock()
    service._release_chat_llm_billing = release

    monkeypatch.setattr("ii_agent.chat.application.turn_loop_service.get_db_session_local", _db_cm)

    result = await service._settle_chat_llm_billing(
        reservation=SimpleNamespace(hold=SimpleNamespace(reservation_id="res-1")),
        user_id="u1",
        session_id="s1",
        run_id="run-1",
        token_record=SimpleNamespace(),
        provider="openai",
        request_kind="chat_response",
        latency_ms=12,
    )

    assert result is None
    release.assert_not_awaited()
    billing.mark_settlement_failed.assert_awaited_once()


@pytest.mark.asyncio
async def test_settle_chat_tool_billing_leaves_hold_on_settlement_failure(monkeypatch):
    @asynccontextmanager
    async def _db_cm():
        yield object()

    billing = SimpleNamespace(
        settle_tool_call=AsyncMock(side_effect=RuntimeError("boom")),
        mark_settlement_failed=AsyncMock(),
    )
    service = LLMTurnLoopService(message_service=FakeMessageService(), llm_billing=billing)
    release = AsyncMock()
    service._release_chat_tool_billing = release

    monkeypatch.setattr("ii_agent.chat.application.turn_loop_service.get_db_session_local", _db_cm)

    result = await service._settle_chat_tool_billing(
        reservation=SimpleNamespace(hold=SimpleNamespace(reservation_id="res-1")),
        user_id="user-1",
        session_id="session-1",
        actual_cost_usd=0.2,
        run_id="run-1",
        tool_name="search_tool",
        billing_context=BillingContextValue.TOOL_CALL,
    )

    assert result is None
    release.assert_not_awaited()
    billing.mark_settlement_failed.assert_awaited_once()


@pytest.mark.asyncio
async def test_settle_chat_llm_billing_raises_when_mark_failed_cannot_persist(monkeypatch):
    @asynccontextmanager
    async def _db_cm():
        yield object()

    billing = SimpleNamespace(
        settle_llm_call=AsyncMock(side_effect=RuntimeError("boom")),
        mark_settlement_failed=AsyncMock(side_effect=RuntimeError("db write failed")),
    )
    service = LLMTurnLoopService(message_service=FakeMessageService(), llm_billing=billing)

    monkeypatch.setattr("ii_agent.chat.application.turn_loop_service.get_db_session_local", _db_cm)

    with pytest.raises(BillingSettlementFinalError, match="persist settlement_failed"):
        await service._settle_chat_llm_billing(
            reservation=SimpleNamespace(hold=SimpleNamespace(reservation_id="res-1")),
            user_id="u1",
            session_id="s1",
            run_id="run-1",
            token_record=SimpleNamespace(),
            provider="openai",
            request_kind="chat_response",
            latency_ms=12,
        )


@pytest.mark.asyncio
async def test_settle_chat_tool_billing_raises_when_mark_failed_cannot_persist(monkeypatch):
    @asynccontextmanager
    async def _db_cm():
        yield object()

    billing = SimpleNamespace(
        settle_tool_call=AsyncMock(side_effect=RuntimeError("boom")),
        mark_settlement_failed=AsyncMock(side_effect=RuntimeError("db write failed")),
    )
    service = LLMTurnLoopService(message_service=FakeMessageService(), llm_billing=billing)

    monkeypatch.setattr("ii_agent.chat.application.turn_loop_service.get_db_session_local", _db_cm)

    with pytest.raises(BillingSettlementFinalError, match="persist settlement_failed"):
        await service._settle_chat_tool_billing(
            reservation=SimpleNamespace(hold=SimpleNamespace(reservation_id="res-1")),
            user_id="user-1",
            session_id="session-1",
            actual_cost_usd=0.2,
            run_id="run-1",
            tool_name="search_tool",
            billing_context=BillingContextValue.TOOL_CALL,
        )


@pytest.mark.asyncio
async def test_settle_chat_llm_billing_marks_failed_when_usage_missing():
    service = LLMTurnLoopService(message_service=FakeMessageService(), llm_billing=object())
    mark_failed = AsyncMock()
    service._mark_billing_settlement_failed = mark_failed

    result = await service._settle_chat_llm_billing(
        reservation=SimpleNamespace(hold=SimpleNamespace(reservation_id="res-1")),
        user_id="u1",
        session_id="s1",
        run_id="run-1",
        token_record=None,
        provider="openai",
        request_kind="chat_response",
        latency_ms=None,
    )

    assert result is None
    mark_failed.assert_awaited_once_with("res-1", "chat_llm_missing_usage")


@pytest.mark.asyncio
async def test_storybook_progress_keeps_tool_reservation_open(monkeypatch):
    async def _noop(*args, **kwargs):
        return None

    async def _compress_context(**kwargs):
        return kwargs["messages"]

    monkeypatch.setattr(
        "ii_agent.chat.application.turn_loop_service.cancel.raise_if_cancelled", _noop
    )
    monkeypatch.setattr(
        "ii_agent.chat.application.turn_loop_service.ContextWindowManager.compress_context_if_needed",
        _compress_context,
    )
    monkeypatch.setattr(
        "ii_agent.chat.application.turn_loop_service.ContextWindowManager.check_and_summarize_after_response",
        _noop,
    )

    service = LLMTurnLoopService(
        message_service=FakeMessageService(),
        llm_billing=object(),
        llm_invocation_repo=FakeInvocationRepo(),
        tool_invocation_repo=FakeInvocationRepo(),
    )
    reservation = SimpleNamespace(hold=SimpleNamespace(reservation_id="res-1"))
    service._reserve_chat_llm_billing = AsyncMock(return_value=None)
    service._settle_chat_llm_billing = AsyncMock(return_value=None)
    service._reserve_chat_tool_billing = AsyncMock(return_value=reservation)
    service._settle_chat_tool_billing = AsyncMock(return_value=None)

    user_message = Message(
        id=uuid4(),
        role=MessageRole.USER,
        session_id="s1",
        parts=[TextContent(text="hello")],
        created_at=0,
        updated_at=0,
    )
    tool = FakeStorybookTool()
    tool.start_celery_generation = AsyncMock(side_effect=tool.start_celery_generation)

    events = []
    async for event in service.run(
        FakeDB(),
        messages=[user_message],
        provider=FakeStorybookProvider(),
        tool_registry={"generate_storybook": tool},
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

    assert any(e.get("type") == "tool_progress" for e in events)
    service._settle_chat_tool_billing.assert_not_awaited()
    kwargs = tool.start_celery_generation.await_args.kwargs
    assert kwargs["run_id"] == "run-1"
    assert kwargs["reservation_id"] == "res-1"
