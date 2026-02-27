from types import SimpleNamespace

from ii_agent.workers.celery import manager


def test_get_celery_container_is_singleton(monkeypatch):
    manager._celery_container = None

    created = []

    def _create():
        container = SimpleNamespace(id=len(created) + 1)
        created.append(container)
        return container

    monkeypatch.setattr("ii_agent.workers.celery.manager.ServiceContainer.create", _create)

    first = manager.get_celery_container()
    second = manager.get_celery_container()

    assert first is second
    assert len(created) == 1
