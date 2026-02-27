from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from e2b.exceptions import NotFoundException

from ii_agent.engine.sandboxes.e2b import (
    E2BSandboxManager,
    e2b_exception_handler,
)
from ii_agent.engine.sandboxes.exceptions import (
    SandboxNotFoundException,
    SandboxNotInitializedError,
    SandboxOperationError,
)
from ii_agent.engine.sandboxes.schemas import SandboxStatus


def _manager() -> E2BSandboxManager:
    return E2BSandboxManager(
        sandbox_id="sb-1",
        session_id="session-1",
        provider_sandbox_id="provider-1",
        status=SandboxStatus.RUNNING,
        sandbox=SimpleNamespace(),
        expired_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_e2b_exception_handler_maps_not_found():
    @e2b_exception_handler
    async def _fn(self):
        raise NotFoundException("not found")

    manager = _manager()
    with pytest.raises(SandboxNotFoundException):
        await _fn(manager)


@pytest.mark.asyncio
async def test_run_command_success_and_error(monkeypatch):
    manager = _manager()
    manager._ensure_sandbox_connection = AsyncMock()

    class _FakeCommandResult:
        def __init__(self, exit_code: int, stdout: str = "", stderr: str = ""):
            self.exit_code = exit_code
            self.stdout = stdout
            self.stderr = stderr

    monkeypatch.setattr("ii_agent.engine.sandboxes.e2b.CommandResult", _FakeCommandResult)

    manager.sandbox = SimpleNamespace(
        commands=SimpleNamespace(run=AsyncMock(return_value=_FakeCommandResult(0, "ok"))),
    )
    output = await manager.run_command("echo ok")
    assert output == "ok"

    manager.sandbox = SimpleNamespace(
        commands=SimpleNamespace(
            run=AsyncMock(return_value=_FakeCommandResult(1, "", "boom"))
        ),
    )
    with pytest.raises(SandboxOperationError):
        await manager.run_command("false")


@pytest.mark.asyncio
async def test_run_python_code_success_and_error(monkeypatch):
    manager = _manager()
    manager._ensure_sandbox_connection = AsyncMock()

    class _FakeExecution:
        def __init__(self, *, text: str = "", error=None):
            self.results = [SimpleNamespace(text=text)]
            self.error = error

    monkeypatch.setattr("ii_agent.engine.sandboxes.e2b.Execution", _FakeExecution)

    manager.sandbox = SimpleNamespace(
        run_code=AsyncMock(return_value=_FakeExecution(text="42")),
    )
    assert await manager.run_python_code("print(42)") == "42"

    manager.sandbox = SimpleNamespace(
        run_code=AsyncMock(
            return_value=_FakeExecution(
                error=SimpleNamespace(name="RuntimeError", value="bad")
            )
        ),
    )
    with pytest.raises(SandboxOperationError):
        await manager.run_python_code("raise RuntimeError")


@pytest.mark.asyncio
async def test_download_file_type_conversion_and_unsupported():
    manager = _manager()
    manager._ensure_sandbox_connection = AsyncMock()

    manager.sandbox = SimpleNamespace(
        files=SimpleNamespace(read=AsyncMock(return_value=b"bytes")),
    )
    assert await manager.download_file("/tmp/a", format="bytes") == b"bytes"

    manager.sandbox = SimpleNamespace(
        files=SimpleNamespace(read=AsyncMock(return_value=bytearray(b"bytes"))),
    )
    assert await manager.download_file("/tmp/a", format="bytes") == b"bytes"

    manager.sandbox = SimpleNamespace(
        files=SimpleNamespace(read=AsyncMock(return_value="text-value")),
    )
    assert await manager.download_file("/tmp/a", format="bytes") == b"text-value"

    manager.sandbox = SimpleNamespace(
        files=SimpleNamespace(read=AsyncMock(return_value=object())),
    )
    with pytest.raises(SandboxOperationError):
        await manager.download_file("/tmp/a", format="text")


@pytest.mark.asyncio
async def test_pause_set_timeout_and_store_cleanup():
    manager = _manager()
    manager._update_sandbox_db = AsyncMock()
    manager.sandbox = SimpleNamespace(
        is_running=AsyncMock(return_value=True),
        beta_pause=AsyncMock(),
        set_timeout=AsyncMock(),
    )
    old_expiry = manager.expired_at

    await manager.pause()
    assert manager.status == SandboxStatus.PAUSED
    manager._update_sandbox_db.assert_awaited()

    await manager.set_timeout(120)
    assert manager.expired_at >= old_expiry + timedelta(seconds=120)

    manager.pause = AsyncMock()
    await manager.store_and_cleanup()
    manager.pause.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_lifecycle_calls_provider_and_updates_db(monkeypatch):
    fake_settings = SimpleNamespace(
        sandbox=SimpleNamespace(
            e2b_template_id="template-1",
            e2b_api_key="api-key",
            timeout_seconds=60,
        ),
    )
    monkeypatch.setattr("ii_agent.engine.sandboxes.e2b.get_settings", lambda: fake_settings)
    monkeypatch.setattr(
        "ii_agent.engine.sandboxes.e2b.AsyncSandbox.beta_create",
        AsyncMock(return_value=SimpleNamespace(sandbox_id="provider-123")),
    )
    update_mock = AsyncMock()
    monkeypatch.setattr(E2BSandboxManager, "_update_sandbox_db", update_mock)

    manager = await E2BSandboxManager.create(
        sandbox_id="sb-1",
        session_id="session-1",
        metadata={"k": "v"},
    )

    assert manager.provider_sandbox_id == "provider-123"
    assert manager.status == SandboxStatus.RUNNING
    update_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_connection_and_directory_helpers(monkeypatch):
    manager = _manager()

    class _State:
        PAUSED = True
        RUNNING = False

    sandbox_info = SimpleNamespace(
        state=_State(),
        end_at=datetime.now(timezone.utc) - timedelta(seconds=120),
    )
    manager.sandbox = SimpleNamespace(
        get_info=AsyncMock(return_value=sandbox_info),
        files=SimpleNamespace(
            make_dir=AsyncMock(return_value=False),
            exists=AsyncMock(return_value=True),
            write=AsyncMock(),
            remove=AsyncMock(),
        ),
    )
    manager._connect = AsyncMock(return_value=manager)
    monkeypatch.setattr(
        "ii_agent.engine.sandboxes.e2b.get_settings",
        lambda: SimpleNamespace(sandbox=SimpleNamespace(e2b_api_key="k", timeout_seconds=30)),
    )

    await manager._ensure_sandbox_connection()
    manager._connect.assert_awaited_once()

    with pytest.raises(SandboxOperationError):
        await manager.create_directory("/tmp/work", exist_ok=False)

    ok = await manager.create_directory("/tmp/work", exist_ok=True)
    assert ok is True
    assert await manager.file_exists("/tmp/work") is True

    assert await manager.upload_file("abc", "/tmp/file.txt") is True
    assert await manager.delete_file("/tmp/file.txt") is True


@pytest.mark.asyncio
async def test_ensure_connection_raises_when_uninitialized():
    manager = E2BSandboxManager(
        sandbox_id="sb-1",
        session_id="session-1",
        provider_sandbox_id="provider-1",
        sandbox=None,
    )

    with pytest.raises(SandboxNotInitializedError):
        await manager._ensure_sandbox_connection()
