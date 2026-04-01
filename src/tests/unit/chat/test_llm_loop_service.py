from types import SimpleNamespace
from uuid import uuid4

import pytest

from ii_agent.billing.schemas import TokenUsage
from ii_agent.chat.application.turn_loop_service import LLMTurnLoopService
from ii_agent.chat.types import (
    EventType,
    FinishReason,
    Message,
    MessageRole,
    RunResponseEvent,
    RunResponseOutput,
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
                usage=TokenUsage(input_tokens=10, output_tokens=5),
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
                    usage=TokenUsage(input_tokens=12, output_tokens=4),
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
                usage=TokenUsage(input_tokens=6, output_tokens=2),
                finish_reason=FinishReason.END_TURN,
                files=[],
                provider_metadata={"provider": "test"},
            ),
        )



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

    service = LLMTurnLoopService(
        message_service=FakeMessageService(),
        llm_billing=None,
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

    service = LLMTurnLoopService(
        message_service=FakeMessageService(),
        llm_billing=None,
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

    service = LLMTurnLoopService(
        message_service=FakeMessageService(),
        llm_billing=None,
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



