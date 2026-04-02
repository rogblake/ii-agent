from types import SimpleNamespace

import pytest
from fastapi import FastAPI

pytest.importorskip("ii_agent.engine.agents.beta.controller.agent_controller")

from ii_agent.integrations.mcp_sse import integration


def test_mount_to_fastapi_skips_when_server_creation_fails(monkeypatch):
    app = FastAPI()
    monkeypatch.setattr(integration, "create_mcp_server_sync", lambda: None)

    result = integration.mount_to_fastapi(app, mount_path="/mcp")

    assert result is None


def test_mount_to_fastapi_mounts_wrapper_app(monkeypatch):
    app = FastAPI()

    class FakeHTTPApp:
        lifespan = object()

    class FakeMCPServer:
        def http_app(self, path="/"):
            return FakeHTTPApp()

    monkeypatch.setattr(integration, "_mcp_app", None)
    monkeypatch.setattr(integration, "_fastmcp_http_app", None)
    monkeypatch.setattr(integration, "create_mcp_server_sync", lambda: FakeMCPServer())

    server = integration.mount_to_fastapi(app, mount_path="/mcp")

    assert server is not None
    assert any(getattr(route, "path", "") == "/mcp" for route in app.routes)
    assert integration.get_mcp_lifespan() is not None
