from __future__ import annotations

import io
import os
from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest

# Ensure modules with import-time model resolution have a default model config.
os.environ.setdefault("LLM_CONFIGS__default__model", "gpt-4o")
os.environ.setdefault("LLM_CONFIGS__default__api_type", "openai")
os.environ.setdefault("LLM_CONFIGS__default__api_key", "test-key")

from ii_agent.core.config.settings import get_settings
from ii_agent.core.storage.base import BaseStorage


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Keep settings singleton isolated across tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class InMemoryStorage(BaseStorage):
    """Simple in-memory storage used in tests."""

    def __init__(self):
        self._objects: dict[str, bytes] = {}

    def write(self, content, path: str, content_type: str | None = None):
        if hasattr(content, "read"):
            payload = content.read()
        else:
            payload = content
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        self._objects[path] = payload

    def write_from_url(
        self, url: str, path: str, content_type: str | None = None
    ) -> str:
        self._objects[path] = f"from:{url}".encode("utf-8")
        return path

    def read(self, path: str):
        return io.BytesIO(self._objects[path])

    def get_download_signed_url(
        self, path: str, expiration_seconds: int = 3600
    ) -> str | None:
        return f"https://signed.local/{path}"

    def get_download_signed_urls_batch(
        self, paths: list[str], expiration_seconds: int = 3600
    ) -> list[str | None]:
        return [f"https://signed.local/{p}" for p in paths]

    def get_upload_signed_url(
        self, path: str, content_type: str, expiration_seconds: int = 3600
    ) -> str:
        return f"https://upload.local/{path}"

    def is_exists(self, path: str) -> bool:
        return path in self._objects

    def get_file_size(self, path: str) -> int:
        return len(self._objects[path])

    def get_public_url(self, path: str) -> str:
        return f"https://public.local/{path}"

    def get_permanent_url(self, path: str) -> str:
        return f"https://permanent.local/{path}"

    def upload_and_get_permanent_url(
        self, content, path: str, content_type: str | None = None
    ) -> str:
        self.write(content, path, content_type)
        return self.get_permanent_url(path)


@pytest.fixture
def in_memory_storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def settings_factory(tmp_path):
    """Return a factory for lightweight Settings-like objects."""

    class AttrDict(dict):
        def __getattr__(self, name):
            try:
                return self[name]
            except KeyError as exc:
                raise AttributeError(name) from exc

        def __setattr__(self, name, value):
            self[name] = value

    base = {
        "environment": "dev",
        "workspace_path": str(tmp_path / "workspace"),
        "workspace_upload_subpath": "uploads",
        "use_container_workspace": False,
        "tool_server_url": "http://tool-server",
        "stripe_return_url": "https://app.local",
        "stripe_success_url": None,
        "stripe_cancel_url": None,
        "jwt_secret_key": "test-secret",
        "access_token_expire_minutes": 15,
        "refresh_token_expire_days": 7,
        "database": {
            "url": "postgresql+asyncpg://postgres:postgres@localhost:5432/ii_agent",
            "pool_size": 10,
            "max_overflow": 20,
            "pool_timeout": 30,
        },
        "redis": {
            "session_url": "redis://localhost:6379/0",
            "session_enabled": False,
        },
        "storage": {
            "provider": "gcs",
            "project_id": "test-project",
            "file_upload_bucket_name": "uploads-bucket",
            "media_bucket_name": "media-bucket",
            "file_store_path": str(tmp_path / "storage"),
        },
        "oauth": {
            "session_secret_key": "session-secret",
            "ii_auth_base": "https://auth.ii.inc",
        },
        "credits": {
            "default_user_credits": 10.0,
            "default_subscription_plan": "free",
            "default_plans_credits": {
                "free": 10.0,
                "plus": 100.0,
                "pro": 250.0,
            },
            "waitlist_enabled": False,
        },
        "stripe": {
            "secret_key": "sk_test_123",
            "webhook_secret": "whsec_123",
            "price_plus_monthly": "price_plus_m",
            "price_plus_annually": "price_plus_a",
            "price_pro_monthly": "price_pro_m",
            "price_pro_annually": "price_pro_a",
            "stripe_portal_return_url": "https://app.local/billing",
        },
        "llm_configs": {},
        "sandbox": {"time_til_clean_up": 3600},
        "mcp": {
            "anthropic_oauth_token_url": "https://mcp.local/oauth/token",
            "anthropic_oauth_client_id": "client-id",
            "anthropic_oauth_redirect_uri": "https://mcp.local/callback",
        },
    }

    def _to_ns(value: Any):
        if isinstance(value, dict):
            return AttrDict({k: _to_ns(v) for k, v in value.items()})
        return value

    def _merge(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
        for key, value in src.items():
            if isinstance(value, dict) and isinstance(dst.get(key), dict):
                _merge(dst[key], value)
            else:
                dst[key] = value
        return dst

    def _factory(**overrides):
        merged = _merge(deepcopy(base), overrides)
        return _to_ns(merged)

    return _factory


@pytest.fixture
def async_session_cm_factory():
    """Create async context managers yielding arbitrary objects."""

    def _factory(value):
        @asynccontextmanager
        async def _cm():
            yield value

        return _cm

    return _factory
