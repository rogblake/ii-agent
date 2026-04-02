from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.agents.sandboxes.e2b import E2BSandbox
from ii_agent.agents.sandboxes.e2b_shell import E2BShell
from ii_agent.agents.sandboxes.shell import ShellSessionRecord, ShellSessionState
from ii_agent.agents.sandboxes.types import SandboxStatus

pytestmark = pytest.mark.unit


def _make_shell_parent() -> MagicMock:
    parent = MagicMock()
    parent.sandbox_id = str(uuid.uuid4())
    parent._config = MagicMock()
    parent._config.workspace_path = "/workspace"
    parent._ensure_sandbox_connection = AsyncMock()
    parent.sandbox = MagicMock()
    parent.sandbox.pty = MagicMock()
    parent.sandbox.pty.send_stdin = AsyncMock()
    return parent


class TestE2BShellCapability:
    def test_e2b_sandbox_exposes_shell_capability(self):
        config = MagicMock()
        manager = E2BSandbox(
            sandbox_id="sandbox-1",
            session_id="session-1",
            provider_sandbox_id="provider-1",
            status=SandboxStatus.RUNNING,
            config=config,
        )

        assert isinstance(manager.shell, E2BShell)

    @pytest.mark.asyncio
    async def test_build_process_input_request_marks_idle_session_busy_when_submitting(self):
        shell = E2BShell(_make_shell_parent())
        record = ShellSessionRecord(
            pid=123,
            cwd="/workspace",
            log_path="/workspace/.ii_agent/pty/build.log",
            state_path="/workspace/.ii_agent/pty/build.state",
            status=ShellSessionState.IDLE,
            prompt_seq=7,
            updated_at="2026-04-02T00:00:00+00:00",
        )

        request = await shell.build_process_input_request(
            record,
            "npm run dev",
            press_enter=True,
        )

        assert request.stdin == b"npm run dev\n"
        assert request.record.status == ShellSessionState.BUSY
        assert request.record.pending_prompt_seq == 8
