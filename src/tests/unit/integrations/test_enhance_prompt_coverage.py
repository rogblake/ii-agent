"""Coverage tests for prompt enhancement router/client helpers."""

from __future__ import annotations

from types import SimpleNamespace
import importlib

import pytest

from ii_agent.billing.types import BillingContextValue, SubjectKind
from ii_agent.core.config.enhance_prompt_config import EnhancePromptConfig
from ii_agent.integrations.enhance_prompt.client import (
    _build_input_text,
    OpenAIEnhancePromptClient,
    create_enhance_prompt_client,
)
from ii_agent.integrations.enhance_prompt.router import EnhancePromptRequest, enhance_prompt


def test_create_enhance_prompt_client_returns_none_without_api_key():
    config = EnhancePromptConfig(openai_api_key=None)
    assert create_enhance_prompt_client(config) is None


@pytest.mark.asyncio
async def test_create_input_text_without_context():
    assert (
        _build_input_text("Summarize", None)
        == "Enhance this request into a detailed prompt: Summarize"
    )


@pytest.mark.asyncio
async def test_create_input_text_with_context():
    assert (
        _build_input_text("Summarize", "for engineers")
        == "Enhance this request into a detailed prompt: Summarize\n\n"
        "Additional context - for engineers"
    )


@pytest.mark.asyncio
async def test_router_returns_fallback_when_client_is_not_configured(monkeypatch):
    request = EnhancePromptRequest(prompt="hello")
    user = SimpleNamespace(id="u")
    db = object()
    llm_execution_service = object()
    router_module = importlib.import_module("ii_agent.integrations.enhance_prompt.router")

    monkeypatch.setattr(
        router_module,
        "get_settings",
        lambda: SimpleNamespace(enhance_prompt=SimpleNamespace()),
    )
    monkeypatch.setattr(
        router_module,
        "create_enhance_prompt_client",
        lambda *_args, **_kwargs: None,
    )

    result = await enhance_prompt(request, db, llm_execution_service, user)
    assert result.enhanced_prompt == "hello"
    assert result.reasoning == "No enhance prompt provider configured"


@pytest.mark.asyncio
async def test_router_maps_client_response(monkeypatch):
    request = EnhancePromptRequest(prompt="hello")
    user = SimpleNamespace(id="u")
    db = object()
    llm_execution_service = object()
    router_module = importlib.import_module("ii_agent.integrations.enhance_prompt.router")

    class FakeResult:
        original_prompt = "hello"
        enhanced_prompt = "hello, please"
        reasoning = "added tone"

    class FakeClient:
        def __init__(self):
            self.bound = None

        def bind_execution_context(self, **kwargs):
            self.bound = kwargs
            return self

        async def enhance(self, prompt, context=None):
            assert prompt == "hello"
            assert context is None
            return FakeResult()

    fake_client = FakeClient()

    monkeypatch.setattr(
        router_module,
        "get_settings",
        lambda: SimpleNamespace(enhance_prompt=SimpleNamespace()),
    )
    monkeypatch.setattr(
        router_module,
        "create_enhance_prompt_client",
        lambda _cfg: fake_client,
    )

    result = await enhance_prompt(request, db, llm_execution_service, user)
    assert result.original_prompt == "hello"
    assert result.enhanced_prompt == "hello, please"
    assert result.reasoning == "added tone"
    assert fake_client.bound == {
        "db": db,
        "llm_execution_service": llm_execution_service,
        "user_id": "u",
    }


@pytest.mark.asyncio
async def test_openai_client_uses_billed_execution_when_context_is_bound(monkeypatch):
    client_module = importlib.import_module("ii_agent.integrations.enhance_prompt.client")

    class FakeExecutionService:
        def __init__(self):
            self.send_once_kwargs = None

        def create_client(self, llm_config):
            self.llm_config = llm_config
            return "client"

        def new_message(self, **kwargs):
            return kwargs

        async def send_once(self, **kwargs):
            self.send_once_kwargs = kwargs
            return SimpleNamespace(content="hello, please")

        def extract_text_content(self, parts):
            return "".join(parts)

    monkeypatch.setattr(client_module, "get_or_generate_request_id", lambda: "req-1")
    client = OpenAIEnhancePromptClient(EnhancePromptConfig(openai_api_key="test-key"))
    execution_service = FakeExecutionService()

    result = await client.bind_execution_context(
        db=object(),
        llm_execution_service=execution_service,
        user_id="user-1",
    ).enhance("hello")

    assert result.enhanced_prompt == "hello, please"
    assert result.reasoning is None
    billing_context = execution_service.send_once_kwargs["billing_context"]
    assert billing_context.scope.subject.kind == SubjectKind.USER
    assert billing_context.scope.subject.id == "user-1"
    assert billing_context.scope.billing_context == BillingContextValue.ENHANCE_PROMPT
    assert billing_context.requested_output_token_cap == 4096
    assert execution_service.send_once_kwargs["usage_key"] == "enhance_prompt:user-1:req-1"


@pytest.mark.asyncio
async def test_openai_client_returns_plain_text_output_directly(monkeypatch):
    client_module = importlib.import_module("ii_agent.integrations.enhance_prompt.client")

    class FakeExecutionService:
        def create_client(self, llm_config):
            self.llm_config = llm_config
            return "client"

        def new_message(self, **kwargs):
            return kwargs

        async def send_once(self, **kwargs):
            return SimpleNamespace(
                content=(
                    "I can help you create a Netflix-style clone. "
                    "Which of these do you mean by clone?"
                )
            )

        def extract_text_content(self, parts):
            return "".join(parts)

    monkeypatch.setattr(client_module, "get_or_generate_request_id", lambda: "req-2")
    client = OpenAIEnhancePromptClient(EnhancePromptConfig(openai_api_key="test-key"))

    result = await client.bind_execution_context(
        db=object(),
        llm_execution_service=FakeExecutionService(),
        user_id="user-2",
    ).enhance("Clone netflix")

    assert result.original_prompt == "Clone netflix"
    assert result.enhanced_prompt == (
        "I can help you create a Netflix-style clone. Which of these do you mean by clone?"
    )
    assert result.reasoning is None


@pytest.mark.asyncio
async def test_openai_client_falls_back_when_model_returns_empty_text(monkeypatch):
    client_module = importlib.import_module("ii_agent.integrations.enhance_prompt.client")

    class FakeExecutionService:
        def create_client(self, llm_config):
            self.llm_config = llm_config
            return "client"

        def new_message(self, **kwargs):
            return kwargs

        async def send_once(self, **kwargs):
            return SimpleNamespace(content="   ")

        def extract_text_content(self, parts):
            return "".join(parts)

    monkeypatch.setattr(client_module, "get_or_generate_request_id", lambda: "req-3")
    client = OpenAIEnhancePromptClient(EnhancePromptConfig(openai_api_key="test-key"))

    result = await client.bind_execution_context(
        db=object(),
        llm_execution_service=FakeExecutionService(),
        user_id="user-3",
    ).enhance("Clone netflix")

    assert result.original_prompt == "Clone netflix"
    assert result.enhanced_prompt == "Clone netflix"
    assert result.reasoning is None
