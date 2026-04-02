from types import SimpleNamespace

import pytest

from ii_agent.celery import utils


class FakeAsyncResult:
    def __init__(self, status="SUCCESS", ready=True, success=True, result=None, info=None):
        self.status = status
        self._ready = ready
        self._success = success
        self._result = result
        self.info = info

    def ready(self):
        return self._ready

    def successful(self):
        return self._success

    def get(self, propagate=False, timeout=None):
        return self._result


@pytest.mark.asyncio
async def test_get_task_status_ready_success(monkeypatch):
    monkeypatch.setattr(utils, "AsyncResult", lambda task_id, app=None: FakeAsyncResult(result={"ok": True}))

    result = await utils.get_task_status("task-1")

    assert result["ready"] is True
    assert result["successful"] is True
    assert result["result"] == {"ok": True}


@pytest.mark.asyncio
async def test_get_task_status_progress(monkeypatch):
    monkeypatch.setattr(
        utils,
        "AsyncResult",
        lambda task_id, app=None: FakeAsyncResult(status="PROGRESS", ready=False, info={"pct": 50}),
    )

    result = await utils.get_task_status("task-1")

    assert result["status"] == "PROGRESS"
    assert result["progress"] == {"pct": 50}


def test_queue_task_passes_routing_options(monkeypatch):
    captured = {}

    def _send_task(name, args, kwargs, queue, countdown, eta, expires, headers):
        captured.update(
            {
                "name": name,
                "args": args,
                "kwargs": kwargs,
                "queue": queue,
                "countdown": countdown,
                "expires": expires,
                "headers": headers,
            }
        )
        return SimpleNamespace(id="task-123")

    monkeypatch.setattr(utils.celery_app, "send_task", _send_task)

    task_id = utils.queue_task(
        "job.name",
        1,
        2,
        queue="high",
        countdown=3,
        expires=30,
        headers={"x": "y"},
        foo="bar",
    )

    assert task_id == "task-123"
    assert captured["queue"] == "high"
    assert captured["kwargs"] == {"foo": "bar"}


@pytest.mark.asyncio
async def test_revoke_task_returns_payload(monkeypatch):
    captured = {}

    def _revoke(task_id, terminate=False, signal="SIGTERM"):
        captured.update({"task_id": task_id, "terminate": terminate, "signal": signal})

    monkeypatch.setattr(utils.celery_app.control, "revoke", _revoke)

    payload = await utils.revoke_task("task-1", terminate=True, signal="SIGKILL")

    assert payload["revoked"] is True
    assert captured["signal"] == "SIGKILL"
