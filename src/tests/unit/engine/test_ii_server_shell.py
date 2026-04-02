from unittest.mock import MagicMock

import pytest

from ii_server.tools.shell.shell_run_command import ShellRunCommand
from ii_server.tools.shell.terminal_manager import ShellResult, _capture_has_shell_prompt


@pytest.mark.parametrize(
    ("current_view", "expected"),
    [
        (["root@sandbox:/workspace$ "], True),
        (["root@sandbox:/workspace# "], True),
        (["done", "root@sandbox:/workspace$ ", ""], True),
        (["done", "", "still running"], False),
        ([], False),
    ],
)
def test_capture_has_shell_prompt_handles_recent_prompt_lines(current_view, expected):
    assert _capture_has_shell_prompt(current_view) is expected


class _ExplodingShellManager:
    def get_all_sessions(self):
        return ["session-1"]

    def run_command(self, *args, **kwargs):
        raise RuntimeError("capture failed")

    def get_session_output(self, session_name):
        return ShellResult(clean_output="prompt is back", ansi_output="prompt is back")


@pytest.mark.asyncio
async def test_shell_run_returns_error_result_for_unexpected_shell_failures():
    command = ShellRunCommand(
        _ExplodingShellManager(),
        workspace_manager=MagicMock(),
    )

    result = await command.execute(
        {
            "session_name": "session-1",
            "command": "echo hello",
            "description": "Echo hello",
        }
    )

    assert result.is_error is True
    assert "Shell command failed: capture failed" in result.llm_content
    assert "prompt is back" in result.llm_content
