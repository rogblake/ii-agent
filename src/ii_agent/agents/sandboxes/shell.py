"""Shared shell session models and helpers for sandbox-backed terminals."""

from __future__ import annotations

from enum import Enum
import re

from pydantic import BaseModel


ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class ShellSessionState(str, Enum):
    BUSY = "busy"
    IDLE = "idle"


class ShellResult(BaseModel):
    clean_output: str
    ansi_output: str


class ShellSessionRecord(BaseModel):
    pid: int
    cwd: str
    log_path: str
    state_path: str
    status: ShellSessionState
    last_command_id: str | None = None
    prompt_seq: int = 0
    pending_prompt_seq: int | None = None
    updated_at: str


class ShellError(Exception):
    pass


class ShellBusyError(ShellError):
    pass


class ShellInvalidSessionNameError(ShellError):
    pass


class ShellSessionNotFoundError(ShellError):
    pass


class ShellSessionExistsError(ShellError):
    pass


class ShellRunDirNotFoundError(ShellError):
    pass


class ShellCommandTimeoutError(ShellError):
    pass


class ShellOperationError(ShellError):
    pass


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def sanitize_shell_output(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    filtered_lines: list[str] = []
    skipping_prompt_function = False
    brace_balance = 0

    for line in normalized.split("\n"):
        plain_line = strip_ansi(line).strip()

        if "__ii_agent_prompt() {" in plain_line:
            skipping_prompt_function = True
            brace_balance = plain_line.count("{") - plain_line.count("}")
            continue

        if skipping_prompt_function:
            brace_balance += plain_line.count("{") - plain_line.count("}")
            if brace_balance <= 0:
                skipping_prompt_function = False
            continue

        if "__ii_agent_prompt" in plain_line:
            continue

        filtered_lines.append(line.replace("__ii_agent_prompt", ""))

    return "\n".join(filtered_lines)
