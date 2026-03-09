from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ii_agent.auth.dependencies import get_current_user
from ii_agent.integrations.enhance_prompt.client import EnhancePromptResult
from ii_agent.integrations.enhance_prompt.router import router

pytestmark = pytest.mark.unit

enhance_prompt_router_module = importlib.import_module(
    "ii_agent.integrations.enhance_prompt.router"
)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    async def _fake_user():
        return SimpleNamespace(id="user-1", is_active=True)

    app.dependency_overrides[get_current_user] = _fake_user
    return app


def test_enhance_prompt_requires_auth():
    app = _make_app()
    app.dependency_overrides.pop(get_current_user, None)

    with TestClient(app) as client:
        response = client.post("/enhance-prompt", json={"prompt": "Make this better"})

    assert response.status_code == 403


def test_enhance_prompt_returns_original_when_provider_not_configured(monkeypatch):
    app = _make_app()
    monkeypatch.setattr(
        enhance_prompt_router_module,
        "create_enhance_prompt_client",
        lambda config: None,
    )

    with TestClient(app) as client:
        response = client.post(
            "/enhance-prompt",
            json={"prompt": "Make this better", "context": "For a landing page"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "original_prompt": "Make this better",
        "enhanced_prompt": "Make this better",
        "reasoning": "No enhance prompt provider configured",
    }


def test_enhance_prompt_returns_client_result(monkeypatch):
    app = _make_app()
    fake_client = SimpleNamespace(
        enhance=AsyncMock(
            return_value=EnhancePromptResult(
                original_prompt="Make this better",
                enhanced_prompt="Write a concise landing page hero for a B2B SaaS product.",
                reasoning="Added audience and output constraints.",
            )
        )
    )
    monkeypatch.setattr(
        enhance_prompt_router_module,
        "create_enhance_prompt_client",
        lambda config: fake_client,
    )

    with TestClient(app) as client:
        response = client.post(
            "/enhance-prompt",
            json={"prompt": "Make this better", "context": "For a B2B SaaS homepage"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "original_prompt": "Make this better",
        "enhanced_prompt": "Write a concise landing page hero for a B2B SaaS product.",
        "reasoning": "Added audience and output constraints.",
    }
    fake_client.enhance.assert_awaited_once_with(
        "Make this better",
        "For a B2B SaaS homepage",
    )
