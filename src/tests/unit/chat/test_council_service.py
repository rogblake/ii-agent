from __future__ import annotations

from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.chat.application.council_service import CouncilService
from ii_agent.chat.types import (
    CouncilModelConfig,
    CouncilPreferences,
    FinishReason,
    Message,
    MessageRole,
    RunResponseOutput,
    TextContent,
)
from ii_agent.billing.usage.models import TokenUsage
from ii_agent.core.config.llm_config import APITypes, LLMConfig
from ii_agent.core.llm.execution_service import LLMExecutionService

pytestmark = pytest.mark.unit


def _make_message(session_id: str = "session-123") -> Message:
    return Message(
        id=uuid4(),
        role=MessageRole.USER,
        session_id=session_id,
        parts=[TextContent(text="How should we solve this?")],
        created_at=0,
        updated_at=0,
    )


def _make_preferences() -> CouncilPreferences:
    return CouncilPreferences(
        enabled=True,
        council_models=[
            CouncilModelConfig(model_id="member-1"),
            CouncilModelConfig(model_id="member-2"),
        ],
        synthesis_model_id="synth-1",
    )


def _make_llm_configs() -> dict[str, LLMConfig]:
    return {
        "member-1": LLMConfig(model="member-1", api_type=APITypes.OPENAI),
        "member-2": LLMConfig(model="member-2", api_type=APITypes.OPENAI),
        "synth-1": LLMConfig(model="synth-1", api_type=APITypes.OPENAI),
    }


def _make_response(content: str) -> RunResponseOutput:
    return RunResponseOutput(
        content=[TextContent(text=content)],
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
        finish_reason=FinishReason.END_TURN,
    )


def _make_execution_service(response_map: dict[str, str]) -> LLMExecutionService:
    """Build a mock LLMExecutionService that returns canned responses by model."""
    svc = LLMExecutionService(llm_billing=None, llm_invocation_repo=None)

    original_send_once = svc.send_once

    async def _mock_send_once(*, client, messages, billing_context=None, usage_key=None, **kwargs):
        # Determine which model this is for from billing_context
        model_id = billing_context.model_id if billing_context else None
        if model_id and model_id in response_map:
            return _make_response(response_map[model_id])
        return _make_response("")

    svc.send_once = _mock_send_once
    return svc


@pytest.mark.asyncio
async def test_stream_council_response_bills_all_models(monkeypatch):
    monkeypatch.setattr(
        "ii_agent.chat.application.council_service.cancel.raise_if_cancelled",
        AsyncMock(return_value=None),
    )

    response_map = {
        "member-1": "Alpha",
        "member-2": "Beta",
        "synth-1": "Combined",
    }

    execution_service = _make_execution_service(response_map)
    db = AsyncMock()

    with patch(
        "ii_agent.chat.application.council_service.get_client",
        side_effect=lambda config: MagicMock(name=f"client-{config.model}"),
    ):
        events = [
            event
            async for event in CouncilService.stream_council_response(
                db=db,
                user_id="user-1",
                messages=[_make_message()],
                user_question="How should we solve this?",
                council_preferences=_make_preferences(),
                llm_configs=_make_llm_configs(),
                model_names={
                    "member-1": "Model One",
                    "member-2": "Model Two",
                    "synth-1": "Synth Model",
                },
                run_id="run-123",
                session_id="session-123",
                llm_execution_service=execution_service,
            )
        ]

    assert any(
        event["type"] == "council_synthesis_complete" and event["content"] == "Combined"
        for event in events
    )

    result_event = next(event for event in events if event["type"] == "council_result")
    assert result_event["member_outputs"] == {
        "member-1": "Alpha",
        "member-2": "Beta",
    }
    assert result_event["synthesis_content"] == "Combined"
    assert result_event["had_error"] is False


@pytest.mark.asyncio
async def test_stream_council_response_handles_member_error(monkeypatch):
    monkeypatch.setattr(
        "ii_agent.chat.application.council_service.cancel.raise_if_cancelled",
        AsyncMock(return_value=None),
    )

    execution_service = LLMExecutionService(llm_billing=None, llm_invocation_repo=None)

    call_count = 0

    async def _mock_send_once(*, client, messages, billing_context=None, usage_key=None, **kwargs):
        nonlocal call_count
        model_id = billing_context.model_id if billing_context else None
        if model_id == "member-1":
            raise RuntimeError("provider boom")
        if model_id == "member-2":
            return _make_response("Stable answer")
        if model_id == "synth-1":
            return _make_response("Summary")
        return _make_response("")

    execution_service.send_once = _mock_send_once
    db = AsyncMock()

    with patch(
        "ii_agent.chat.application.council_service.get_client",
        side_effect=lambda config: MagicMock(name=f"client-{config.model}"),
    ):
        events = [
            event
            async for event in CouncilService.stream_council_response(
                db=db,
                user_id="user-1",
                messages=[_make_message()],
                user_question="How should we solve this?",
                council_preferences=_make_preferences(),
                llm_configs=_make_llm_configs(),
                model_names={
                    "member-1": "Model One",
                    "member-2": "Model Two",
                    "synth-1": "Synth Model",
                },
                run_id="run-456",
                session_id="session-123",
                llm_execution_service=execution_service,
            )
        ]

    assert any(
        event["type"] == "council_member_error"
        and event["model_id"] == "member-1"
        and event["error"] == "provider boom"
        for event in events
    )

    result_event = next(event for event in events if event["type"] == "council_result")
    assert result_event["member_outputs"] == {"member-2": "Stable answer"}
    assert result_event["synthesis_content"] == "Summary"
    assert result_event["had_error"] is True
