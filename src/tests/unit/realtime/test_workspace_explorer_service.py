from __future__ import annotations

import asyncio
import queue
import uuid
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from ii_agent.agent.events.models import EventType
from ii_agent.agent.sandboxes.schemas import SandboxStatus
from ii_agent.agent.sandboxes.workspace_explorer_service import (
    WorkspaceExplorerService,
    _WatcherState,
)

pytestmark = pytest.mark.unit


class _FakeTree:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self):
        return self._payload


class _FakeEvent:
    def __init__(self, change_type: str, name: str):
        self.type = SimpleNamespace(value=change_type)
        self.name = name


def _service() -> WorkspaceExplorerService:
    svc = WorkspaceExplorerService(
        sandbox_service=MagicMock(),
        session_service=MagicMock(),
    )
    svc.bind_event_stream(AsyncMock())
    return svc


def _session_info() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4())


# ── ensure_watching ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_watching_does_nothing_when_no_event_stream():
    svc = WorkspaceExplorerService(
        sandbox_service=MagicMock(), session_service=MagicMock()
    )
    await svc.ensure_watching(session_info=_session_info())
    assert not svc._watchers


@pytest.mark.asyncio
async def test_ensure_watching_does_nothing_when_no_sandbox():
    svc = _service()
    with patch.object(svc, "_resolve_sandbox_record", AsyncMock(return_value=None)):
        await svc.ensure_watching(session_info=_session_info())
    assert not svc._watchers


@pytest.mark.asyncio
async def test_ensure_watching_registers_session_on_existing_watcher():
    svc = _service()
    svc._watchers["sandbox-1"] = _WatcherState(
        provider_id="sandbox-1", session_ids={"old-session"}
    )
    session = _session_info()
    sandbox_record = SimpleNamespace(provider_sandbox_id="sandbox-1")

    with patch.object(svc, "_resolve_sandbox_record", AsyncMock(return_value=sandbox_record)):
        await svc.ensure_watching(session_info=session)

    assert str(session.id) in svc._watchers["sandbox-1"].session_ids


@pytest.mark.asyncio
async def test_ensure_watching_starts_watcher_when_not_running():
    svc = _service()
    session = _session_info()
    sandbox_record = SimpleNamespace(provider_sandbox_id="sandbox-1")

    with (
        patch.object(svc, "_resolve_sandbox_record", AsyncMock(return_value=sandbox_record)),
        patch.object(svc, "_start_watcher", AsyncMock()) as start,
    ):
        await svc.ensure_watching(session_info=session)

    start.assert_awaited_once_with("sandbox-1", str(session.id), sandbox_record)


# ── Debounce scheduling ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_debounce_schedules_flush_and_coalesces():
    svc = _service()
    state = _WatcherState(provider_id="sandbox-1")
    svc._watchers["sandbox-1"] = state

    assert state.debounce_task is None
    svc._schedule_flush("sandbox-1")
    assert state.debounce_task is not None

    first = state.debounce_task
    svc._schedule_flush("sandbox-1")
    assert state.debounce_task is first

    first.cancel()
    try:
        await first
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_debounce_skips_unknown_sandbox():
    svc = _service()
    svc._schedule_flush("unknown")  # should not raise


# ── Flush ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_flush_publishes_changes_to_sessions():
    svc = _service()
    sandbox_manager = AsyncMock()
    sandbox_manager.list_files_with_contents.return_value = (
        _FakeTree({"name": "workspace", "type": "directory", "children": []}),
        {},
    )

    session_id = "00000000-0000-0000-0000-000000000001"
    state = _WatcherState(
        provider_id="sandbox-1",
        sandbox_manager=sandbox_manager,
        session_ids={session_id},
    )
    state.event_queue.put_nowait(_FakeEvent("CREATE", "app.py"))

    event_stream = AsyncMock()
    svc.bind_event_stream(event_stream)

    await svc._flush("sandbox-1", state)

    event_stream.publish.assert_awaited_once()
    evt = event_stream.publish.await_args.args[0]
    assert evt.type == EventType.FILE_TREE_UPDATE
    assert evt.content["changes"] == [
        {"type": "create", "name": "app.py", "path": "/workspace/app.py"}
    ]
    assert "tree" in evt.content


@pytest.mark.asyncio
async def test_flush_skips_tree_refresh_for_write_only():
    svc = _service()
    sandbox_manager = AsyncMock()
    state = _WatcherState(
        provider_id="sandbox-1",
        sandbox_manager=sandbox_manager,
        session_ids={"00000000-0000-0000-0000-000000000001"},
    )
    state.event_queue.put_nowait(_FakeEvent("WRITE", "/workspace/app.py"))

    event_stream = AsyncMock()
    svc.bind_event_stream(event_stream)

    await svc._flush("sandbox-1", state)

    evt = event_stream.publish.await_args.args[0]
    assert "tree" not in evt.content
    sandbox_manager.list_files_with_contents.assert_not_awaited()


# ── Watcher start ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_watcher_sets_up_watch_dir():
    svc = _service()
    watch_handle = MagicMock()
    sandbox_manager = SimpleNamespace(
        get_info=AsyncMock(
            return_value=SimpleNamespace(status=SandboxStatus.RUNNING)
        ),
        _ensure_sandbox_connection=AsyncMock(),
        sandbox=SimpleNamespace(
            files=SimpleNamespace(watch_dir=AsyncMock(return_value=watch_handle))
        ),
        read_file_content=AsyncMock(),
    )

    with patch.object(
        svc, "_connect_sandbox",
        AsyncMock(return_value=(sandbox_manager, None, None)),
    ):
        await svc._start_watcher(
            "sandbox-1",
            "sess-1",
            SimpleNamespace(provider_sandbox_id="sandbox-1"),
        )

    assert "sandbox-1" in svc._watchers
    sandbox_manager.sandbox.files.watch_dir.assert_awaited_once_with(
        "/workspace",
        on_event=ANY,
        on_exit=ANY,
        timeout=0,
        recursive=True,
    )


@pytest.mark.asyncio
async def test_start_watcher_does_nothing_on_sandbox_unavailable():
    svc = _service()

    with patch.object(
        svc, "_connect_sandbox",
        AsyncMock(return_value=(None, "Sandbox is not running", "paused")),
    ):
        await svc._start_watcher(
            "sandbox-1",
            "sess-1",
            SimpleNamespace(provider_sandbox_id="sandbox-1"),
        )

    assert "sandbox-1" not in svc._watchers


# ── Cleanup ──────────────────────────────────────────────────────


def test_cleanup_watcher_removes_state():
    svc = _service()
    svc._watchers["sandbox-1"] = _WatcherState(provider_id="sandbox-1")
    svc._cleanup_watcher("sandbox-1")
    assert "sandbox-1" not in svc._watchers


@pytest.mark.asyncio
async def test_shutdown_stops_all_watchers():
    svc = _service()
    svc._watchers["sandbox-1"] = _WatcherState(provider_id="sandbox-1")
    svc._watchers["sandbox-2"] = _WatcherState(provider_id="sandbox-2")

    await svc.shutdown()

    assert not svc._watchers
