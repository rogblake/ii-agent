from __future__ import annotations

from uuid import uuid4
from unittest.mock import AsyncMock, patch

import pytest

from ii_agent.chat.application.council_service import CouncilService
from ii_agent.chat.types import (
    CouncilModelConfig,
    CouncilPreferences,
    EventType,
    Message,
    MessageRole,
    RunResponseEvent,
    TextContent,
)
from ii_agent.core.config.llm_config import APITypes, LLMConfig

pytestmark = pytest.mark.unit


class RecordingProvider:
    def __init__(self, events: list[RunResponseEvent], terminal_error: Exception | None = None):
        self._events = events
        self._terminal_error = terminal_error
        self.calls: list[dict] = []

    async def stream(self, **kwargs):
        self.calls.append(kwargs)
        for event in self._events:
            yield event
        if self._terminal_error:
            raise self._terminal_error


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


@pytest.mark.asyncio
async def test_stream_council_response_passes_session_id_to_synthesis_provider(monkeypatch):
    monkeypatch.setattr(
        "ii_agent.chat.application.council_service.cancel.raise_if_cancelled",
        AsyncMock(return_value=None),
    )

    providers = {
        "member-1": RecordingProvider(
            [RunResponseEvent(type=EventType.CONTENT_DELTA, content="Alpha")]
        ),
        "member-2": RecordingProvider(
            [RunResponseEvent(type=EventType.CONTENT_DELTA, content="Beta")]
        ),
        "synth-1": RecordingProvider(
            [RunResponseEvent(type=EventType.CONTENT_DELTA, content="Combined")]
        ),
    }

    with patch(
        "ii_agent.chat.application.council_service.LLMProviderFactory.create_provider",
        side_effect=lambda config: providers[config.model],
    ):
        events = [
            event
            async for event in CouncilService.stream_council_response(
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
            )
        ]

    assert providers["synth-1"].calls[0]["session_id"] == "session-123"
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
async def test_stream_council_response_preserves_partial_output_when_member_errors(monkeypatch):
    monkeypatch.setattr(
        "ii_agent.chat.application.council_service.cancel.raise_if_cancelled",
        AsyncMock(return_value=None),
    )

    providers = {
        "member-1": RecordingProvider(
            [RunResponseEvent(type=EventType.CONTENT_DELTA, content="Partial answer")],
            terminal_error=RuntimeError("provider boom"),
        ),
        "member-2": RecordingProvider(
            [RunResponseEvent(type=EventType.CONTENT_DELTA, content="Stable answer")]
        ),
        "synth-1": RecordingProvider(
            [RunResponseEvent(type=EventType.CONTENT_DELTA, content="Summary")]
        ),
    }

    with patch(
        "ii_agent.chat.application.council_service.LLMProviderFactory.create_provider",
        side_effect=lambda config: providers[config.model],
    ):
        events = [
            event
            async for event in CouncilService.stream_council_response(
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
            )
        ]

    assert any(
        event["type"] == "council_member_error"
        and event["model_id"] == "member-1"
        and event["error"] == "provider boom"
        for event in events
    )

    result_event = next(event for event in events if event["type"] == "council_result")
    assert result_event["member_outputs"] == {
        "member-1": "Partial answer",
        "member-2": "Stable answer",
    }
    assert result_event["synthesis_content"] == "Summary"
    assert result_event["had_error"] is True
