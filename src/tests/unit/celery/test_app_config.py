from types import SimpleNamespace

from ii_agent.celery import app as celery_app_module


def test_broker_url_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://custom:6379/5")

    assert celery_app_module.get_celery_broker_url() == "redis://custom:6379/5"


def test_broker_url_maps_redis_db_to_2(monkeypatch):
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.setattr(
        celery_app_module,
        "get_settings",
        lambda: SimpleNamespace(redis=SimpleNamespace(session_url="redis://localhost:6379/0")),
    )

    assert celery_app_module.get_celery_broker_url() == "redis://localhost:6379/2"


def test_result_backend_defaults_to_broker(monkeypatch):
    monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)
    monkeypatch.setattr(celery_app_module, "get_celery_broker_url", lambda: "redis://x/2")

    assert celery_app_module.get_celery_result_backend() == "redis://x/2"
