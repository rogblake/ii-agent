from contextlib import contextmanager
from types import SimpleNamespace

from ii_agent.workers.celery.decorators import with_task_context


class _FakeLogger:
    def __init__(self):
        self.ctx = None

    @contextmanager
    def contextualize(self, **ctx):
        self.ctx = ctx
        yield


def test_with_task_context_injects_headers(monkeypatch):
    fake_logger = _FakeLogger()
    monkeypatch.setattr("ii_agent.workers.celery.decorators.logger", fake_logger)

    @with_task_context
    def _task(self, value):
        return value * 2

    task_self = SimpleNamespace(
        request=SimpleNamespace(
            id="task-1",
            headers={"session_id": "s1", "user_id": "u1", "run_id": "r1"},
        )
    )

    result = _task(task_self, 21)

    assert result == 42
    assert fake_logger.ctx["request_id"] == "task-1"
    assert fake_logger.ctx["session_id"] == "s1"


def test_with_task_context_handles_missing_headers(monkeypatch):
    fake_logger = _FakeLogger()
    monkeypatch.setattr("ii_agent.workers.celery.decorators.logger", fake_logger)

    @with_task_context
    def _task(self):
        return "ok"

    task_self = SimpleNamespace(request=SimpleNamespace(id="task-2", headers=None))

    assert _task(task_self) == "ok"
    assert fake_logger.ctx["request_id"] == "task-2"
