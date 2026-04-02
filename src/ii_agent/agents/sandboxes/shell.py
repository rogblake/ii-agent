"""Shared shell session models and helpers for sandbox-backed terminals."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
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


@dataclass(slots=True)
class ShellExecutionRequest:
    record: "ShellSessionRecord"
    stdin: bytes
    log_offset: int | None = None
    expected_prompt_seq: int | None = None


class Shell(ABC):
    """Provider runtime backend for persistent shell sessions."""

    @property
    @abstractmethod
    def workspace_path(self) -> str:
        """Return the workspace root inside the sandbox."""

    @property
    @abstractmethod
    def max_timeout(self) -> int:
        """Return the maximum supported shell command timeout."""

    @property
    @abstractmethod
    def session_output_tail_bytes(self) -> int:
        """Return the number of bytes to tail for full session output."""

    @property
    @abstractmethod
    def command_output_tail_bytes(self) -> int:
        """Return the number of bytes to tail for command-specific output."""

    @property
    @abstractmethod
    def poll_interval(self) -> float:
        """Return the polling interval used for shell prompt checks."""

    @abstractmethod
    def validate_session_name(self, session_name: str) -> None:
        """Validate a user-provided shell session name."""

    @abstractmethod
    async def normalize_directory(
        self,
        directory: str,
    ) -> str:
        """Normalize and validate a working directory inside the workspace."""

    @abstractmethod
    async def create_session_record(
        self,
        session_name: str,
        start_directory: str,
        timeout: int = 60,
    ) -> "ShellSessionRecord":
        """Create and initialize a PTY-backed shell session record."""

    @abstractmethod
    async def delete_session(
        self,
        session_name: str,
        record: "ShellSessionRecord",
    ) -> None:
        """Delete a PTY-backed shell session."""

    @abstractmethod
    async def is_session_live(
        self,
        record: "ShellSessionRecord",
    ) -> bool:
        """Return whether the PTY and state file for a session are still present."""

    @abstractmethod
    async def refresh_session_record(
        self,
        record: "ShellSessionRecord",
    ) -> tuple["ShellSessionRecord", bool]:
        """Refresh prompt/cwd/status information from runtime state."""

    @abstractmethod
    async def build_command_request(
        self,
        record: "ShellSessionRecord",
        command: str,
        run_dir: str | None = None,
    ) -> ShellExecutionRequest:
        """Prepare a command to send to an existing shell session."""

    @abstractmethod
    async def build_interrupt_request(
        self,
        record: "ShellSessionRecord",
    ) -> ShellExecutionRequest:
        """Prepare a Ctrl+C interrupt for an existing shell session."""

    @abstractmethod
    async def build_process_input_request(
        self,
        record: "ShellSessionRecord",
        data: str,
        press_enter: bool,
    ) -> ShellExecutionRequest:
        """Prepare stdin to send to an existing shell session."""

    @abstractmethod
    async def send_stdin(
        self,
        session_name: str,
        record: "ShellSessionRecord",
        data: bytes,
    ) -> None:
        """Send raw stdin bytes to a shell session PTY."""

    @abstractmethod
    async def wait_for_prompt(
        self,
        record: "ShellSessionRecord",
        *,
        minimum_prompt_seq: int,
        timeout: int,
    ) -> "ShellSessionRecord":
        """Wait for the shell prompt and return the refreshed record."""

    @abstractmethod
    async def read_command_output(
        self,
        record: "ShellSessionRecord",
        *,
        start_offset: int | None = None,
    ) -> ShellResult:
        """Read output for a specific command execution."""

    @abstractmethod
    async def read_session_output(
        self,
        record: "ShellSessionRecord",
    ) -> ShellResult:
        """Read the latest full output for a shell session."""


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
