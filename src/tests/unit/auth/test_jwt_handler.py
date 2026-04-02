from types import SimpleNamespace
import importlib

from ii_agent.auth.jwt_handler import JWTHandler


def test_create_and_verify_access_token(monkeypatch):
    jwt_module = importlib.import_module("ii_agent.auth.jwt_handler")
    monkeypatch.setattr(
        jwt_module,
        "get_settings",
        lambda: SimpleNamespace(
            jwt_secret_key="secret",
            access_token_expire_minutes=15,
            refresh_token_expire_days=7,
        ),
    )
    handler = JWTHandler()

    token = handler.create_access_token("user-1", "user@example.com")
    payload = handler.verify_access_token(token)

    assert payload["user_id"] == "user-1"
    assert payload["type"] == "access"


def test_verify_token_returns_none_for_malformed_token(monkeypatch):
    jwt_module = importlib.import_module("ii_agent.auth.jwt_handler")
    monkeypatch.setattr(
        jwt_module,
        "get_settings",
        lambda: SimpleNamespace(
            jwt_secret_key="secret",
            access_token_expire_minutes=15,
            refresh_token_expire_days=7,
        ),
    )
    handler = JWTHandler()

    assert handler.verify_token("not-a-jwt") is None


def test_expired_access_token_returns_none(monkeypatch):
    jwt_module = importlib.import_module("ii_agent.auth.jwt_handler")
    monkeypatch.setattr(
        jwt_module,
        "get_settings",
        lambda: SimpleNamespace(
            jwt_secret_key="secret",
            access_token_expire_minutes=-1,
            refresh_token_expire_days=7,
        ),
    )
    handler = JWTHandler()

    token = handler.create_access_token("user-1", "user@example.com")

    assert handler.verify_access_token(token) is None
