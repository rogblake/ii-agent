from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from ii_agent import app as app_module

pytestmark = pytest.mark.smoke


def test_app_startup_and_health_route(monkeypatch, settings_factory):
    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    monkeypatch.setattr(app_module, "create_lifespan", lambda: _noop_lifespan)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings_factory())

    asgi_app = app_module.create_app()

    with TestClient(asgi_app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
