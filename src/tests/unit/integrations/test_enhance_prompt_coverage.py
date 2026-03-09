"""Coverage tests for prompt enhancement router/client helpers."""
from __future__ import annotations

from types import SimpleNamespace
import importlib

import pytest

from ii_agent.core.config.enhance_prompt_config import EnhancePromptConfig
from ii_agent.integrations.enhance_prompt.client import (
    _build_input_text,
    _extract_json_payload,
    create_enhance_prompt_client,
)
from ii_agent.integrations.enhance_prompt.router import EnhancePromptRequest, enhance_prompt


def test_create_enhance_prompt_client_returns_none_without_api_key():
    config = EnhancePromptConfig(openai_api_key=None)
    assert create_enhance_prompt_client(config) is None


@pytest.mark.asyncio
async def test_create_input_text_without_context():
    assert _build_input_text("Summarize", None) == "Prompt:\nSummarize"


@pytest.mark.asyncio
async def test_create_input_text_with_context():
    assert _build_input_text("Summarize", "for engineers") == "Prompt:\nSummarize\n\nContext:\nfor engineers"


@pytest.mark.asyncio
async def test_extract_json_payload_parses_wrapped_json():
    payload = _extract_json_payload('prefix text {"enhanced_prompt":"x","reasoning":"y"} suffix')
    assert payload == {"enhanced_prompt": "x", "reasoning": "y"}


@pytest.mark.asyncio
async def test_extract_json_payload_fails_without_json():
    with pytest.raises(ValueError):
        _extract_json_payload("not json at all")


@pytest.mark.asyncio
async def test_router_returns_fallback_when_client_is_not_configured(monkeypatch):
    request = EnhancePromptRequest(prompt="hello")
    user = SimpleNamespace(id="u")
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

    result = await enhance_prompt(request, user)
    assert result.enhanced_prompt == "hello"
    assert result.reasoning == "No enhance prompt provider configured"


@pytest.mark.asyncio
async def test_router_maps_client_response(monkeypatch):
    request = EnhancePromptRequest(prompt="hello")
    user = SimpleNamespace(id="u")
    router_module = importlib.import_module("ii_agent.integrations.enhance_prompt.router")

    class FakeResult:
        original_prompt = "hello"
        enhanced_prompt = "hello, please"
        reasoning = "added tone"

    class FakeClient:
        async def enhance(self, prompt, context=None):
            assert prompt == "hello"
            assert context is None
            return FakeResult()

    monkeypatch.setattr(
        router_module,
        "get_settings",
        lambda: SimpleNamespace(enhance_prompt=SimpleNamespace()),
    )
    monkeypatch.setattr(
        router_module,
        "create_enhance_prompt_client",
        lambda _cfg: FakeClient(),
    )

    result = await enhance_prompt(request, user)
    assert result.original_prompt == "hello"
    assert result.enhanced_prompt == "hello, please"
    assert result.reasoning == "added tone"
