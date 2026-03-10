from __future__ import annotations

import pytest

from ii_agent.billing.usage.models import TokenUsage
from ii_agent.chat.types import FinishReason, RunResponseOutput, TextContent
from ii_agent.core.config.llm_config import APITypes, LLMConfig
from ii_agent.utils import prompt_generator


class FakeLLMExecutionService:
    def __init__(self, response=None, send_once_error: Exception | None = None):
        self.response = response
        self.send_once_error = send_once_error
        self.create_client_calls = []
        self.send_once_calls = []

    def create_client(self, llm_config):
        self.create_client_calls.append(llm_config)
        return "fake-client"

    async def send_once(self, **kwargs):
        self.send_once_calls.append(kwargs)
        if self.send_once_error is not None:
            raise self.send_once_error
        return self.response

    def extract_text_content(self, parts):
        return "".join(
            part.text for part in parts if isinstance(part, TextContent)
        ).strip()


@pytest.mark.asyncio
async def test_enhance_user_prompt_success_includes_file_context():
    response = RunResponseOutput(
        content=[TextContent(text="  polished prompt  ")],
        usage=TokenUsage(),
        finish_reason=FinishReason.END_TURN,
    )
    service = FakeLLMExecutionService(response=response)
    config = LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI)

    success, message, enhanced = await prompt_generator.enhance_user_prompt(
        llm_execution_service=service,
        llm_config=config,
        user_input="Build a dashboard",
        files=["./app/main.py", "README.md"],
    )

    assert success is True
    assert message == "Prompt enhanced successfully"
    assert enhanced == "polished prompt"
    assert service.create_client_calls == [config]
    assert service.send_once_calls, "send_once should be called"

    user_message = service.send_once_calls[0]["messages"][1]
    user_prompt = user_message.content()
    assert user_prompt is not None
    assert "- /app/main.py" in user_prompt.text
    assert "- README.md" in user_prompt.text


@pytest.mark.asyncio
async def test_enhance_user_prompt_success_without_file_context():
    response = RunResponseOutput(
        content=[TextContent(text="no-context prompt")],
        usage=TokenUsage(),
        finish_reason=FinishReason.END_TURN,
    )
    service = FakeLLMExecutionService(response=response)
    config = LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI)

    success, message, enhanced = await prompt_generator.enhance_user_prompt(
        llm_execution_service=service,
        llm_config=config,
        user_input="General request",
        files=[],
    )

    assert success is True
    assert message == "Prompt enhanced successfully"
    assert enhanced == "no-context prompt"
    user_message = service.send_once_calls[0]["messages"][1]
    assert "Referenced files:" not in user_message.content().text


@pytest.mark.asyncio
async def test_enhance_user_prompt_returns_error_tuple_on_exception():
    service = FakeLLMExecutionService(
        send_once_error=RuntimeError("provider unavailable")
    )
    config = LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI)

    success, message, enhanced = await prompt_generator.enhance_user_prompt(
        llm_execution_service=service,
        llm_config=config,
        user_input="Retry this",
        files=[],
    )

    assert success is False
    assert enhanced is None
    assert "Error enhancing prompt: provider unavailable" in message
