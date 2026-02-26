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


def test_worker_pool_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("CELERY_WORKER_POOL", "prefork")
    monkeypatch.setattr(celery_app_module.platform, "system", lambda: "Darwin")

    assert celery_app_module.get_celery_worker_pool() == "prefork"


def test_worker_pool_defaults_to_solo_on_darwin(monkeypatch):
    monkeypatch.delenv("CELERY_WORKER_POOL", raising=False)
    monkeypatch.setattr(celery_app_module.platform, "system", lambda: "Darwin")

    assert celery_app_module.get_celery_worker_pool() == "solo"


def test_worker_pool_defaults_to_prefork_on_non_darwin(monkeypatch):
    monkeypatch.delenv("CELERY_WORKER_POOL", raising=False)
    monkeypatch.setattr(celery_app_module.platform, "system", lambda: "Linux")

    assert celery_app_module.get_celery_worker_pool() == "prefork"


def test_worker_concurrency_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("CELERY_WORKER_CONCURRENCY", "7")

    assert celery_app_module.get_celery_worker_concurrency("solo") == 7


def test_worker_concurrency_defaults_to_one_for_solo(monkeypatch):
    monkeypatch.delenv("CELERY_WORKER_CONCURRENCY", raising=False)

    assert celery_app_module.get_celery_worker_concurrency("solo") == 1


def test_worker_concurrency_defaults_to_four_for_prefork(monkeypatch):
    monkeypatch.delenv("CELERY_WORKER_CONCURRENCY", raising=False)

    assert celery_app_module.get_celery_worker_concurrency("prefork") == 4
