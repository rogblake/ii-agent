"""E2B Sandbox provider implementation.

Pure provider — all database persistence is handled by :class:`SandboxService`.
"""

import asyncio
import os
import posixpath
import shlex
import stat as _stat_mod
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import PurePosixPath
from typing import IO, Any, AsyncIterator, Dict, List, Literal, Optional

from e2b import CommandResult, PtySize, SandboxState
from e2b.exceptions import (
    AuthenticationException,
    NotFoundException,
    TimeoutException,
)
from e2b_code_interpreter import AsyncSandbox
from e2b_code_interpreter.models import Execution
from fastmcp import Client
from ii_agent.agents.sandboxes.base import Sandbox
from ii_agent.agents.sandboxes.exceptions import (
    SandboxAuthenticationError,
    SandboxNotFoundException,
    SandboxNotInitializedError,
    SandboxOperationError,
    SandboxTimeoutException,
)
from ii_agent.agents.sandboxes.schemas import (
    EXCLUDED_DIRS,
    INLINE_CONTENT_MAX_SIZE,
    INLINE_CONTENT_TOTAL_MAX,
    MAX_FILE_CONTENT_SIZE,
    FileContentResponse,
    FileTreeNode,
    FileUpload,
    SandboxFileInfo,
    SandboxInfo,
    detect_language,
    guess_mime_type,
    is_binary_file_path,
    is_image_file_path,
)
from ii_agent.agents.sandboxes.shell import (
    ShellBusyError,
    ShellCommandTimeoutError,
    ShellInvalidSessionNameError,
    ShellOperationError,
    ShellResult,
    ShellRunDirNotFoundError,
    ShellSessionExistsError,
    ShellSessionNotFoundError,
    ShellSessionRecord,
    ShellSessionState,
    sanitize_shell_output,
    strip_ansi,
)
from ii_agent.agents.sandboxes.terminal import (
    LiveTerminalHandle,
    LiveTerminalNotFoundError,
    TerminalDataCallback,
)
from ii_agent.agents.sandboxes.types import SandboxProviderType, SandboxStatus
from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.core.logger import logger

_DEFAULT_SHELL_TIMEOUT = 60
_MAX_SHELL_TIMEOUT = 180
_SHELL_POLL_INTERVAL = 0.25
_DEFAULT_PROMPT_PREFIX = "root@sandbox"
_PROMPT_FORMAT = r"\[\033[01;32m\]{PREFIX}\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ ".format(
    PREFIX=_DEFAULT_PROMPT_PREFIX
)
_SHELL_STORAGE_DIRNAME = ".ii_agent/pty"
_SHELL_LOG_TAIL_BYTES = 65536
_SHELL_OUTPUT_TAIL_BYTES = 131072
_SHELL_UTILITY_TIMEOUT = 30
_ENV_SOURCE_CMD = "source /app/.user_env.sh"
_ENV_SOURCE_SAFE_CMD = f"{_ENV_SOURCE_CMD} >/dev/null 2>&1 || true"
_SHELL_LOCKS: dict[str, asyncio.Lock] = {}


def _is_dir_entry(entry: Any) -> bool:
    """Check whether a filesystem entry from E2B is a directory."""
    raw_type = entry.type
    if raw_type is not None:
        type_val = raw_type.value if hasattr(raw_type, "value") else str(raw_type)
        if type_val.lower() in ("dir", "directory", "file_type_directory"):
            return True
    if hasattr(entry, "mode") and entry.mode is not None:
        if _stat_mod.S_ISDIR(entry.mode):
            return True
    return False


def e2b_exception_handler(func):
    """Decorator to handle E2B-specific exceptions and convert to sandbox exceptions."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except NotFoundException as e:
            sandbox_id = "unknown"
            if args and hasattr(args[0], "sandbox_id"):
                sandbox_id = args[0].sandbox_id
            raise SandboxNotFoundException(str(sandbox_id)) from e
        except AuthenticationException as e:
            raise SandboxAuthenticationError(str(e)) from e
        except TimeoutException as e:
            sandbox_id = "unknown"
            if args and hasattr(args[0], "sandbox_id"):
                sandbox_id = args[0].sandbox_id
            raise SandboxTimeoutException(str(sandbox_id), func.__name__) from e
        except (
            SandboxNotFoundException,
            SandboxAuthenticationError,
            SandboxTimeoutException,
            SandboxNotInitializedError,
            SandboxOperationError,
        ):
            raise
        except Exception as e:
            raise SandboxOperationError(func.__name__, str(e)) from e

    return wrapper


class E2BLiveTerminalHandle(LiveTerminalHandle):
    """Provider-agnostic wrapper around E2B PTY handles."""

    def __init__(self, *, pty, handle) -> None:
        self._pty = pty
        self._handle = handle

    @property
    def pid(self) -> int:
        return self._handle.pid

    async def send_input(self, data: bytes) -> None:
        try:
            await self._pty.send_stdin(self.pid, data)
        except NotFoundException as exc:
            raise LiveTerminalNotFoundError(f"PTY process {self.pid} not found") from exc

    async def resize(self, cols: int, rows: int) -> None:
        try:
            await self._pty.resize(self.pid, PtySize(cols=cols, rows=rows))
        except NotFoundException as exc:
            raise LiveTerminalNotFoundError(f"PTY process {self.pid} not found") from exc

    async def kill(self) -> bool:
        try:
            return await self._handle.kill()
        except NotFoundException as exc:
            raise LiveTerminalNotFoundError(f"PTY process {self.pid} not found") from exc

    async def disconnect(self) -> None:
        await self._handle.disconnect()

    async def wait(self) -> int | None:
        try:
            result = await self._handle.wait()
        except NotFoundException as exc:
            raise LiveTerminalNotFoundError(f"PTY process {self.pid} not found") from exc
        return getattr(result, "exit_code", None)


class E2BSandbox(Sandbox):
    """E2B cloud sandbox implementation.

    Handles only provider-level operations (create, connect, pause,
    run commands, file I/O).  No database awareness.
    """

    PROVIDER: SandboxProviderType = SandboxProviderType.E2B

    def __init__(
        self,
        sandbox_id: str,
        session_id: str,
        provider_sandbox_id: str,
        status: SandboxStatus = SandboxStatus.NOT_INITIALIZED,
        metadata: Optional[Dict[str, Any]] = None,
        sandbox: Optional[AsyncSandbox] = None,
        expired_at: Optional[datetime] = None,
        config: Optional[Settings] = None,
    ):
        super().__init__(
            sandbox_id=sandbox_id,
            session_id=session_id,
            provider_sandbox_id=provider_sandbox_id,
            status=status,
            metadata=metadata,
            expired_at=expired_at,
        )
        self.sandbox = sandbox
        self.mcp_client: Optional[Client] = None
        self._config = config or get_settings()

    # ── Info ──────────────────────────────────────────────────────────────

    def get_provider_id(self) -> str:
        return self.provider_sandbox_id

    @property
    def upload_path(self) -> str:
        return self._config.workspace_upload_path

    async def get_info(self) -> SandboxInfo:
        vscode_url = None
        if self.status == SandboxStatus.RUNNING and self.sandbox:
            try:
                vscode_url = await self.expose_port(self._config.vscode_port)
            except Exception:
                pass
        return SandboxInfo(
            id=self.sandbox_id,
            session_id=self.session_id,
            status=self.status,
            expired_at=self.expired_at,
            provider=SandboxProviderType.E2B,
            vscode_url=vscode_url,
        )

    @staticmethod
    def _discard_pty_data(_: bytes) -> None:
        return None

    @staticmethod
    def _shell_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_shell_output(text: str) -> str:
        return sanitize_shell_output(text)

    @staticmethod
    def _validate_shell_session_name(session_name: str) -> None:
        if not session_name or not session_name.replace("_", "").replace("-", "").isalnum():
            raise ShellInvalidSessionNameError(
                "Invalid session name. Only alphanumeric characters, hyphens, and underscores are allowed."
            )

    def _get_shell_lock(self):
        return _SHELL_LOCKS.setdefault(self.sandbox_id, asyncio.Lock())

    def _get_shell_storage_dir(self) -> str:
        return str(PurePosixPath(get_settings().workspace_path) / _SHELL_STORAGE_DIRNAME)

    def _get_shell_log_path(self, session_name: str) -> str:
        return str(PurePosixPath(self._get_shell_storage_dir()) / f"{session_name}.log")

    def _get_shell_state_path(self, session_name: str) -> str:
        return str(PurePosixPath(self._get_shell_storage_dir()) / f"{session_name}.state")

    async def _run_shell_utility_command(
        self,
        command: str,
        *,
        timeout: int = _SHELL_UTILITY_TIMEOUT,
    ) -> str:
        await self._ensure_sandbox_connection()
        result = await self.sandbox.commands.run(
            command,
            background=False,
            timeout=timeout,
        )

        if not isinstance(result, CommandResult):
            raise ShellOperationError(
                "run_shell_utility_command",
                f"Unexpected result: {result}",
            )

        if result.exit_code != 0:
            error_msg = result.stderr or result.stdout or f"Exit code: {result.exit_code}"
            raise ShellOperationError("run_shell_utility_command", error_msg)

        return result.stdout

    async def _load_provider_data(self) -> dict[str, Any]:
        from ii_agent.agents.sandboxes.repository import SandboxRepository
        from ii_agent.core.db import get_db_session_local

        async with get_db_session_local() as db_session:
            sandbox_record = await SandboxRepository().get_by_id(
                db_session, uuid.UUID(self.sandbox_id)
            )
            if sandbox_record is None:
                raise ShellOperationError(
                    "load_provider_data",
                    f"Sandbox record not found: {self.sandbox_id}",
                )
            provider_data = dict(sandbox_record.provider_data or {})

        self.metadata = provider_data
        return provider_data

    async def _persist_provider_data(self, provider_data: dict[str, Any]) -> None:
        from ii_agent.agents.sandboxes.repository import SandboxRepository
        from ii_agent.core.db import get_db_session_local

        async with get_db_session_local() as db_session:
            sandbox_record = await SandboxRepository().get_by_id(
                db_session, uuid.UUID(self.sandbox_id)
            )
            if sandbox_record is None:
                raise ShellOperationError(
                    "persist_provider_data",
                    f"Sandbox record not found: {self.sandbox_id}",
                )
            sandbox_record.provider_data = provider_data

        self.metadata = provider_data

    async def _load_shell_sessions(self) -> dict[str, ShellSessionRecord]:
        provider_data = await self._load_provider_data()
        raw_sessions = provider_data.get("pty_sessions") or {}
        if not isinstance(raw_sessions, dict):
            return {}

        sessions: dict[str, ShellSessionRecord] = {}
        for session_name, raw_record in raw_sessions.items():
            try:
                sessions[session_name] = ShellSessionRecord.model_validate(raw_record)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Invalid PTY session metadata for sandbox %s session %s: %s",
                    self.sandbox_id,
                    session_name,
                    exc,
                )
        return sessions

    async def _save_shell_sessions(self, sessions: dict[str, ShellSessionRecord]) -> None:
        provider_data = await self._load_provider_data()
        provider_data["pty_sessions"] = {
            session_name: record.model_dump(mode="json")
            for session_name, record in sessions.items()
        }
        await self._persist_provider_data(provider_data)

    async def _normalize_shell_directory(self, directory: str) -> str:
        normalized = posixpath.normpath(directory.strip())
        normalized = str(PurePosixPath(normalized))
        if not normalized.startswith("/"):
            raise ShellRunDirNotFoundError(
                "Start directory must be an absolute path inside the workspace."
            )

        workspace_path = str(PurePosixPath(get_settings().workspace_path))
        if normalized != workspace_path and not normalized.startswith(f"{workspace_path}/"):
            raise ShellRunDirNotFoundError(f"Directory must be inside workspace: {workspace_path}")

        quoted_dir = shlex.quote(normalized)
        try:
            await self._run_shell_utility_command(f"test -d {quoted_dir}")
        except ShellOperationError as exc:
            raise ShellRunDirNotFoundError(
                f"Directory does not exist or is not a directory: {normalized}"
            ) from exc

        return normalized

    async def _read_shell_state(
        self,
        state_path: str,
    ) -> tuple[int | None, str | None]:
        await self._ensure_sandbox_connection()
        try:
            if not await self.sandbox.files.exists(state_path):
                return None, None
            content = await self.sandbox.files.read(state_path, format="text")
        except Exception:  # noqa: BLE001
            return None, None

        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")

        lines = content.splitlines()
        if len(lines) < 2:
            return None, None

        try:
            prompt_seq = int(lines[0].strip())
        except ValueError:
            return None, None

        cwd = lines[1].strip() or None
        return prompt_seq, cwd

    async def _wait_for_shell_prompt(
        self,
        state_path: str,
        *,
        minimum_prompt_seq: int,
        timeout: int,
    ) -> tuple[int, str | None]:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            prompt_seq, cwd = await self._read_shell_state(state_path)
            if prompt_seq is not None and prompt_seq >= minimum_prompt_seq:
                return prompt_seq, cwd
            await asyncio.sleep(_SHELL_POLL_INTERVAL)

        raise ShellCommandTimeoutError(
            f"Timed out waiting for shell prompt after {timeout} seconds."
        )

    async def _get_file_size(self, file_path: str) -> int:
        quoted_path = shlex.quote(file_path)
        output = await self._run_shell_utility_command(
            f"if [ -f {quoted_path} ]; then wc -c < {quoted_path}; else echo 0; fi"
        )
        try:
            return int(output.strip() or "0")
        except ValueError:
            return 0

    async def _read_shell_log(
        self,
        log_path: str,
        *,
        start_offset: int | None = None,
        max_bytes: int,
    ) -> str:
        file_size = await self._get_file_size(log_path)
        if file_size <= 0:
            return ""

        quoted_path = shlex.quote(log_path)
        if start_offset is not None:
            start_offset = max(start_offset, 0)
            bytes_remaining = file_size - start_offset
            if bytes_remaining <= 0:
                return ""
            if bytes_remaining <= max_bytes:
                command = f"tail -c +{start_offset + 1} {quoted_path}"
            else:
                command = f"tail -c {max_bytes} {quoted_path}"
        else:
            command = f"tail -c {max_bytes} {quoted_path}"

        output = await self._run_shell_utility_command(
            f"if [ -f {quoted_path} ]; then {command}; fi"
        )
        return self._normalize_shell_output(output)

    async def _get_shell_result(
        self,
        log_path: str,
        *,
        start_offset: int | None = None,
        max_bytes: int,
    ) -> ShellResult:
        ansi_output = await self._read_shell_log(
            log_path,
            start_offset=start_offset,
            max_bytes=max_bytes,
        )
        clean_output = strip_ansi(ansi_output)
        return ShellResult(
            clean_output=clean_output,
            ansi_output=ansi_output,
        )

    async def _is_shell_session_live(self, record: ShellSessionRecord) -> bool:
        await self._ensure_sandbox_connection()
        try:
            handle = await self.sandbox.pty.connect(
                record.pid,
                on_data=self._discard_pty_data,
                timeout=0,
            )
            await handle.disconnect()
        except NotFoundException:
            return False
        except Exception as exc:  # noqa: BLE001
            raise ShellOperationError(
                "is_shell_session_live",
                f"Failed to connect to PTY {record.pid}: {exc}",
            ) from exc

        return await self.sandbox.files.exists(record.state_path)

    async def _refresh_shell_session_record(
        self,
        session_name: str,
        record: ShellSessionRecord,
        *,
        persist: bool = False,
    ) -> ShellSessionRecord:
        prompt_seq, cwd = await self._read_shell_state(record.state_path)
        changed = False

        if prompt_seq is not None and prompt_seq != record.prompt_seq:
            record.prompt_seq = prompt_seq
            changed = True
        if cwd and cwd != record.cwd:
            record.cwd = cwd
            changed = True

        if record.pending_prompt_seq is not None:
            if prompt_seq is not None and prompt_seq >= record.pending_prompt_seq:
                record.pending_prompt_seq = None
                record.status = ShellSessionState.IDLE
                changed = True
            elif record.status != ShellSessionState.BUSY:
                record.status = ShellSessionState.BUSY
                changed = True
        elif record.status != ShellSessionState.IDLE:
            record.status = ShellSessionState.IDLE
            changed = True

        if changed:
            record.updated_at = self._shell_timestamp()
            if persist:
                sessions = await self._load_shell_sessions()
                sessions[session_name] = record
                await self._save_shell_sessions(sessions)

        return record

    async def _remove_stale_shell_session(self, session_name: str) -> None:
        sessions = await self._load_shell_sessions()
        if session_name in sessions:
            sessions.pop(session_name, None)
            await self._save_shell_sessions(sessions)

    def _build_outer_shell_bootstrap(
        self,
        *,
        log_path: str,
        state_path: str,
    ) -> str:
        storage_dir = self._get_shell_storage_dir()
        lines = [
            f"export II_AGENT_LOG_PATH={shlex.quote(log_path)}",
            f"export II_AGENT_STATE_PATH={shlex.quote(state_path)}",
            f"mkdir -p {shlex.quote(storage_dir)}",
            f": > {shlex.quote(log_path)}",
            f"rm -f {shlex.quote(state_path)} {shlex.quote(state_path + '.tmp')}",
            "export TERM='xterm-256color'",
            f"script -q -f {shlex.quote(log_path)} -c 'bash --noprofile --norc -i'",
        ]
        return "\n".join(lines) + "\n"

    def _build_inner_shell_bootstrap(self) -> str:
        prompt_value = shlex.quote(_PROMPT_FORMAT)
        return (
            "export TERM='xterm-256color'\n"
            f"export PS1={prompt_value}\n"
            "__ii_agent_prompt() {\n"
            f"  {_ENV_SOURCE_SAFE_CMD}\n"
            "  II_AGENT_PROMPT_SEQ=$(( ${II_AGENT_PROMPT_SEQ:-0} + 1 ))\n"
            '  __ii_agent_state_tmp="${II_AGENT_STATE_PATH}.tmp"\n'
            "  {\n"
            "    printf '%s\\n' \"$II_AGENT_PROMPT_SEQ\"\n"
            "    pwd\n"
            '  } > "$__ii_agent_state_tmp"\n'
            '  mv "$__ii_agent_state_tmp" "$II_AGENT_STATE_PATH"\n'
            "}\n"
            "PROMPT_COMMAND='__ii_agent_prompt'\n"
            "clear\n"
        )

    async def get_all_shell_sessions(self) -> list[str]:
        async with self._get_shell_lock():
            sessions = await self._load_shell_sessions()
            live_sessions: dict[str, ShellSessionRecord] = {}
            stale_session_names: list[str] = []

            for session_name, record in sessions.items():
                if await self._is_shell_session_live(record):
                    live_sessions[session_name] = record
                else:
                    stale_session_names.append(session_name)

            if stale_session_names:
                logger.info(
                    "Pruning stale PTY sessions for sandbox %s: %s",
                    self.sandbox_id,
                    stale_session_names,
                )
                await self._save_shell_sessions(live_sessions)

            return sorted(live_sessions.keys())

    async def create_shell_session(
        self,
        session_name: str,
        start_directory: str,
        timeout: int = _DEFAULT_SHELL_TIMEOUT,
    ) -> None:
        self._validate_shell_session_name(session_name)
        start_directory = await self._normalize_shell_directory(start_directory)

        async with self._get_shell_lock():
            sessions = await self._load_shell_sessions()
            existing_record = sessions.get(session_name)
            if existing_record is not None:
                if await self._is_shell_session_live(existing_record):
                    raise ShellSessionExistsError(f"Session '{session_name}' already exists")
                sessions.pop(session_name, None)
                await self._save_shell_sessions(sessions)

            await self._ensure_sandbox_connection()
            terminal = await self.sandbox.pty.create(
                PtySize(cols=120, rows=40),
                on_data=self._discard_pty_data,
                cwd=start_directory,
                timeout=0,
            )

            log_path = self._get_shell_log_path(session_name)
            state_path = self._get_shell_state_path(session_name)

            try:
                await self.sandbox.pty.send_stdin(
                    terminal.pid,
                    self._build_outer_shell_bootstrap(
                        log_path=log_path,
                        state_path=state_path,
                    ).encode(),
                )
                await asyncio.sleep(0.5)
                await self.sandbox.pty.send_stdin(
                    terminal.pid,
                    self._build_inner_shell_bootstrap().encode(),
                )
                prompt_seq, cwd = await self._wait_for_shell_prompt(
                    state_path,
                    minimum_prompt_seq=1,
                    timeout=timeout,
                )
            except Exception:
                try:
                    await self.sandbox.pty.kill(terminal.pid)
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "Failed to clean up PTY %s during shell session bootstrap",
                        terminal.pid,
                        exc_info=True,
                    )
                raise
            finally:
                await terminal.disconnect()

            sessions[session_name] = ShellSessionRecord(
                pid=terminal.pid,
                cwd=cwd or start_directory,
                log_path=log_path,
                state_path=state_path,
                status=ShellSessionState.IDLE,
                prompt_seq=prompt_seq,
                updated_at=self._shell_timestamp(),
            )
            await self._save_shell_sessions(sessions)

    async def delete_shell_session(self, session_name: str) -> None:
        async with self._get_shell_lock():
            sessions = await self._load_shell_sessions()
            record = sessions.get(session_name)
            if record is None:
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

            await self._ensure_sandbox_connection()
            try:
                await self.sandbox.pty.kill(record.pid)
            except NotFoundException:
                logger.info("PTY %s already exited for session %s", record.pid, session_name)

            sessions.pop(session_name, None)
            await self._save_shell_sessions(sessions)

    async def run_shell_command(
        self,
        session_name: str,
        command: str,
        run_dir: str | None = None,
        timeout: int = _DEFAULT_SHELL_TIMEOUT,
        wait_for_output: bool = True,
    ) -> ShellResult:
        if timeout > _MAX_SHELL_TIMEOUT:
            raise ShellOperationError(
                "run_shell_command",
                f"Timeout must be less than {_MAX_SHELL_TIMEOUT} seconds",
            )

        normalized_run_dir = None
        if run_dir:
            normalized_run_dir = await self._normalize_shell_directory(run_dir)

        sessions = await self._load_shell_sessions()
        existing_record = sessions.get(session_name)
        default_directory = normalized_run_dir or (
            existing_record.cwd if existing_record is not None else get_settings().workspace_path
        )

        if existing_record is None:
            try:
                await self.create_shell_session(session_name, default_directory, timeout=timeout)
            except ShellSessionExistsError:
                pass
        elif not await self._is_shell_session_live(existing_record):
            await self._remove_stale_shell_session(session_name)
            try:
                await self.create_shell_session(session_name, default_directory, timeout=timeout)
            except ShellSessionExistsError:
                pass

        async with self._get_shell_lock():
            sessions = await self._load_shell_sessions()
            record = sessions.get(session_name)
            if record is None:
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

            record = await self._refresh_shell_session_record(session_name, record)
            if record.status == ShellSessionState.BUSY:
                raise ShellBusyError("Session is busy, the last command is not finished.")

            log_offset = await self._get_file_size(record.log_path)
            commands_to_send: list[str] = []
            if normalized_run_dir:
                commands_to_send.append(f"cd {shlex.quote(normalized_run_dir)}")
            if _ENV_SOURCE_CMD not in command:
                commands_to_send.append(_ENV_SOURCE_SAFE_CMD)
            commands_to_send.append("clear")
            commands_to_send.append(command)

            command_id = str(uuid.uuid4())
            expected_prompt_seq = record.prompt_seq + len(commands_to_send)
            record.status = ShellSessionState.BUSY
            record.last_command_id = command_id
            record.pending_prompt_seq = expected_prompt_seq
            record.updated_at = self._shell_timestamp()
            sessions[session_name] = record
            await self._save_shell_sessions(sessions)

            try:
                await self.sandbox.pty.send_stdin(
                    record.pid,
                    ("\n".join(commands_to_send) + "\n").encode(),
                )
            except NotFoundException as exc:
                sessions.pop(session_name, None)
                await self._save_shell_sessions(sessions)
                raise ShellSessionNotFoundError(
                    f"Session '{session_name}' is no longer available"
                ) from exc

        if not wait_for_output:
            return await self.get_shell_session_output(session_name)

        await self._wait_for_shell_prompt(
            record.state_path,
            minimum_prompt_seq=expected_prompt_seq,
            timeout=timeout,
        )

        async with self._get_shell_lock():
            sessions = await self._load_shell_sessions()
            latest_record = sessions.get(session_name)
            if latest_record is None:
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")
            latest_record = await self._refresh_shell_session_record(
                session_name,
                latest_record,
            )
            sessions[session_name] = latest_record
            await self._save_shell_sessions(sessions)

        return await self._get_shell_result(
            record.log_path,
            start_offset=log_offset,
            max_bytes=_SHELL_OUTPUT_TAIL_BYTES,
        )

    async def kill_shell_command(
        self,
        session_name: str,
        timeout: int = _DEFAULT_SHELL_TIMEOUT,
    ) -> ShellResult:
        async with self._get_shell_lock():
            sessions = await self._load_shell_sessions()
            record = sessions.get(session_name)
            if record is None:
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

            if not await self._is_shell_session_live(record):
                sessions.pop(session_name, None)
                await self._save_shell_sessions(sessions)
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

            log_offset = await self._get_file_size(record.log_path)
            current_prompt_seq = record.prompt_seq
            record.status = ShellSessionState.BUSY
            record.pending_prompt_seq = current_prompt_seq + 1
            record.updated_at = self._shell_timestamp()
            sessions[session_name] = record
            await self._save_shell_sessions(sessions)

            try:
                await self.sandbox.pty.send_stdin(record.pid, b"\x03")
            except NotFoundException as exc:
                sessions.pop(session_name, None)
                await self._save_shell_sessions(sessions)
                raise ShellSessionNotFoundError(
                    f"Session '{session_name}' is no longer available"
                ) from exc

        await self._wait_for_shell_prompt(
            record.state_path,
            minimum_prompt_seq=current_prompt_seq + 1,
            timeout=timeout,
        )

        async with self._get_shell_lock():
            sessions = await self._load_shell_sessions()
            latest_record = sessions.get(session_name)
            if latest_record is None:
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")
            latest_record = await self._refresh_shell_session_record(
                session_name,
                latest_record,
            )
            sessions[session_name] = latest_record
            await self._save_shell_sessions(sessions)

        return await self._get_shell_result(
            record.log_path,
            start_offset=log_offset,
            max_bytes=_SHELL_OUTPUT_TAIL_BYTES,
        )

    async def get_shell_session_state(self, session_name: str) -> ShellSessionState:
        sessions = await self._load_shell_sessions()
        record = sessions.get(session_name)
        if record is None:
            raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

        if not await self._is_shell_session_live(record):
            await self._remove_stale_shell_session(session_name)
            raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

        record = await self._refresh_shell_session_record(
            session_name,
            record,
            persist=True,
        )
        return record.status

    async def get_shell_session_output(self, session_name: str) -> ShellResult:
        sessions = await self._load_shell_sessions()
        record = sessions.get(session_name)
        if record is None:
            raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

        if not await self._is_shell_session_live(record):
            await self._remove_stale_shell_session(session_name)
            raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

        await self._refresh_shell_session_record(
            session_name,
            record,
            persist=True,
        )
        return await self._get_shell_result(
            record.log_path,
            max_bytes=_SHELL_LOG_TAIL_BYTES,
        )

    async def write_to_shell_process(
        self,
        session_name: str,
        data: str,
        press_enter: bool,
    ) -> ShellResult:
        async with self._get_shell_lock():
            sessions = await self._load_shell_sessions()
            record = sessions.get(session_name)
            if record is None:
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

            if not await self._is_shell_session_live(record):
                sessions.pop(session_name, None)
                await self._save_shell_sessions(sessions)
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

            stdin_data = data + ("\n" if press_enter else "")
            try:
                await self.sandbox.pty.send_stdin(record.pid, stdin_data.encode())
            except NotFoundException as exc:
                sessions.pop(session_name, None)
                await self._save_shell_sessions(sessions)
                raise ShellSessionNotFoundError(
                    f"Session '{session_name}' is no longer available"
                ) from exc

        await asyncio.sleep(_SHELL_POLL_INTERVAL)
        return await self.get_shell_session_output(session_name)

    async def get_status(self) -> SandboxStatus:
        if self.sandbox is None:
            return SandboxStatus.INITIALIZING
        sandbox_info = await AsyncSandbox.get_info(
            sandbox_id=self.provider_sandbox_id,
            api_key=self._config.sandbox.e2b_api_key,
            domain=self._config.sandbox.e2b_domain,
        )
        return self._to_sandbox_status(sandbox_info.state)

    # ── Lifecycle ─────────────────────────────────────────────────────────

    @classmethod
    async def create(
        cls,
        sandbox_id: str,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "E2BSandbox":
        """Provision a new E2B sandbox."""
        cfg = get_settings()

        sandbox_metadata = {
            "ii_sandbox_id": sandbox_id,
            "session_id": session_id,
            "template_id": cfg.sandbox.e2b_template_id,
            "env": cfg.environment,
        }
        if metadata:
            sandbox_metadata.update(metadata)

        expired_at = datetime.now(timezone.utc) + timedelta(seconds=cfg.sandbox.timeout_seconds)

        sandbox = await AsyncSandbox.beta_create(
            template=cfg.sandbox.e2b_template_id,
            api_key=cfg.sandbox.e2b_api_key,
            metadata=sandbox_metadata,
            auto_pause=cfg.sandbox.auto_pause,
            timeout=cfg.sandbox.timeout_seconds,
            domain=cfg.sandbox.e2b_domain,
        )

        instance = cls(
            sandbox_id=sandbox_id,
            session_id=session_id,
            provider_sandbox_id=sandbox.sandbox_id,
            sandbox=sandbox,
            metadata=sandbox_metadata,
            status=SandboxStatus.RUNNING,
            expired_at=expired_at,
            config=cfg,
        )

        logger.info(
            f"Created E2B sandbox {sandbox_id} (provider: {sandbox.sandbox_id}) "
            f"with timeout {cfg.sandbox.timeout_seconds}s"
        )
        return instance

    @classmethod
    async def connect(
        cls,
        sandbox_id: str,
        session_id: str,
        provider_sandbox_id: str,
    ) -> "E2BSandbox":
        """Connect to an existing E2B sandbox."""
        cfg = get_settings()

        sandbox = await AsyncSandbox.connect(
            sandbox_id=provider_sandbox_id,
            api_key=cfg.sandbox.e2b_api_key,
            timeout=cfg.sandbox.timeout_seconds,
            domain=cfg.sandbox.e2b_domain,
        )
        sandbox_info = await sandbox.get_info()
        status = cls._to_sandbox_status(sandbox_info.state)

        return cls(
            sandbox_id=sandbox_id,
            session_id=session_id,
            provider_sandbox_id=sandbox.sandbox_id,
            sandbox=sandbox,
            metadata=sandbox_info.metadata,
            status=status,
            expired_at=sandbox_info.end_at,
            config=cfg,
        )

    @e2b_exception_handler
    async def pause(self) -> None:
        is_running = await self.sandbox.is_running()
        if is_running:
            await self.sandbox.beta_pause()
            self.status = SandboxStatus.PAUSED
            logger.info(f"Paused sandbox {self.sandbox_id} (provider: {self.provider_sandbox_id})")

    @e2b_exception_handler
    async def set_timeout(self, timeout_seconds: int) -> None:
        await self.sandbox.set_timeout(timeout=timeout_seconds)
        self.expired_at = self.expired_at + timedelta(seconds=timeout_seconds)
        logger.debug(
            f"Set timeout for sandbox (provider: {self.provider_sandbox_id}): {timeout_seconds}s"
        )

    # ── Command execution ─────────────────────────────────────────────────

    @e2b_exception_handler
    async def run_command(
        self,
        command: str,
        background: bool = False,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
        **kwargs,
    ) -> str:
        await self._ensure_sandbox_connection()
        result = await self.sandbox.commands.run(
            command,
            background=background,
            timeout=timeout,
            cwd=cwd,
            **kwargs,
        )

        if not isinstance(result, CommandResult):
            raise SandboxOperationError("run_command", f"Unexpected result: {result}")

        if result.exit_code != 0:
            error_msg = result.stderr or result.stdout or f"Exit code: {result.exit_code}"
            raise SandboxOperationError("run_command", f"Command failed: {error_msg}")

        return result.stdout

    @e2b_exception_handler
    async def run_python_code(self, code: str, timeout: int = 120) -> str:
        await self._ensure_sandbox_connection()
        result = await self.sandbox.run_code(
            code,
            language="python",
            background=False,
            timeout=timeout,
            cwd=None,
        )

        if not isinstance(result, Execution):
            raise SandboxOperationError("run_python_code", f"Unexpected result: {result}")

        if result.error:
            raise SandboxOperationError(
                "run_python_code",
                f"Execution failed:{result.error.name} {result.error.value}",
            )

        return result.results[0].text or ""

    async def create_live_terminal(
        self,
        *,
        cols: int,
        rows: int,
        cwd: str,
        on_data: TerminalDataCallback,
        envs: dict[str, str] | None = None,
        timeout: float | None = 0,
    ) -> LiveTerminalHandle:
        await self._ensure_sandbox_connection()
        handle = await self.sandbox.pty.create(
            PtySize(cols=cols, rows=rows),
            on_data=on_data,
            cwd=cwd,
            envs=envs,
            timeout=timeout,
        )
        return E2BLiveTerminalHandle(pty=self.sandbox.pty, handle=handle)

    # ── File operations ───────────────────────────────────────────────────

    @e2b_exception_handler
    async def read_file(self, file_path: str) -> str:
        await self._ensure_sandbox_connection()
        return await self.sandbox.files.read(file_path, format="text")

    @e2b_exception_handler
    async def write_file(
        self,
        file_path: str,
        content: str | bytes | IO,
    ) -> SandboxFileInfo:
        await self._ensure_sandbox_connection()
        write_info = await self.sandbox.files.write(file_path, content)
        return SandboxFileInfo(name=write_info.name, type="file", path=file_path)

    @e2b_exception_handler
    async def write_files(self, files: List[FileUpload]) -> List[SandboxFileInfo]:
        await self._ensure_sandbox_connection()
        files_data = [{"path": file.path, "data": file.content} for file in files]
        results = await self.sandbox.files.write_files(files_data)
        return [SandboxFileInfo(name=r.name, type=r.type, path=r.path) for r in results]

    @e2b_exception_handler
    async def upload_file(
        self,
        file_content: str | bytes | IO,
        remote_file_path: str,
    ) -> bool:
        await self._ensure_sandbox_connection()
        if await self.sandbox.files.exists(remote_file_path):
            logger.warning(f"File {remote_file_path} already exists, overwriting")
        await self.sandbox.files.write(remote_file_path, file_content)
        return True

    @e2b_exception_handler
    async def download_file(
        self,
        remote_file_path: str,
        format: Literal["text", "bytes"] = "text",
    ) -> Optional[str | bytes]:
        await self._ensure_sandbox_connection()
        content = await self.sandbox.files.read(path=remote_file_path, format=format)
        if isinstance(content, bytes):
            return content
        elif isinstance(content, bytearray):
            return bytes(content)
        elif isinstance(content, str):
            return content if format == "text" else content.encode("utf-8")
        else:
            raise SandboxOperationError(
                "download_file", f"Unsupported content type: {type(content)}"
            )

    async def download_file_stream(
        self,
        remote_file_path: str,
    ) -> AsyncIterator[bytes]:
        await self._ensure_sandbox_connection()
        return await self.sandbox.files.read(path=remote_file_path, format="stream")

    @e2b_exception_handler
    async def delete_file(self, file_path: str) -> bool:
        await self._ensure_sandbox_connection()
        await self.sandbox.files.remove(file_path)
        return True

    @e2b_exception_handler
    async def create_directory(
        self,
        directory_path: str,
        exist_ok: bool = False,
    ) -> bool:
        await self._ensure_sandbox_connection()
        created = await self.sandbox.files.make_dir(directory_path)
        if not created and not exist_ok:
            raise SandboxOperationError(
                "create_directory", f"Directory {directory_path} already exists"
            )
        return True

    @e2b_exception_handler
    async def file_exists(self, file_path: str) -> bool:
        await self._ensure_sandbox_connection()
        return await self.sandbox.files.exists(file_path)

    # ── File tree & content ────────────────────────────────────────────────

    async def list_files_recursive(
        self,
        path: str,
        max_depth: int = 10,
        _current_depth: int = 0,
    ) -> FileTreeNode:
        """Recursively list all files/dirs under *path*, returning a tree."""
        await self._ensure_sandbox_connection()

        basename = os.path.basename(path.rstrip("/")) or path
        entries = await self.sandbox.files.list(path)

        children: list[FileTreeNode] = []
        for entry in entries:
            entry_name = entry.name
            entry_path = f"{path.rstrip('/')}/{entry_name}"
            is_dir = _is_dir_entry(entry)

            if is_dir:
                if entry_name in EXCLUDED_DIRS:
                    continue
                if _current_depth < max_depth:
                    try:
                        subtree = await self.list_files_recursive(
                            entry_path,
                            max_depth=max_depth,
                            _current_depth=_current_depth + 1,
                        )
                        children.append(subtree)
                    except Exception:
                        children.append(
                            FileTreeNode(
                                name=entry_name, path=entry_path, type="directory", children=[]
                            )
                        )
                else:
                    children.append(
                        FileTreeNode(
                            name=entry_name, path=entry_path, type="directory", children=[]
                        )
                    )
            else:
                children.append(
                    FileTreeNode(
                        name=entry_name,
                        path=entry_path,
                        type="file",
                        size=entry.size if hasattr(entry, "size") else None,
                    )
                )

        children.sort(key=lambda n: (0 if n.type == "directory" else 1, n.name.lower()))
        return FileTreeNode(name=basename, path=path, type="directory", children=children)

    @e2b_exception_handler
    async def list_files_with_contents(
        self,
        path: str,
        max_depth: int = 10,
        inline_content_max_depth: int | None = None,
    ) -> tuple[FileTreeNode, dict[str, dict[str, str]]]:
        """Return the recursive file tree and pre-read contents of small text files."""
        contents: dict[str, dict[str, str]] = {}
        total_bytes = 0

        async def _collect(node: FileTreeNode, *, current_depth: int) -> None:
            nonlocal total_bytes
            if node.type == "directory" and node.children:
                for child in node.children:
                    await _collect(child, current_depth=current_depth + 1)
            elif node.type == "file":
                if (
                    inline_content_max_depth is not None
                    and current_depth > inline_content_max_depth
                ):
                    return
                if is_binary_file_path(node.path):
                    return
                file_size = node.size if node.size is not None else INLINE_CONTENT_MAX_SIZE + 1
                if file_size > INLINE_CONTENT_MAX_SIZE:
                    return
                if total_bytes + file_size > INLINE_CONTENT_TOTAL_MAX:
                    return
                try:
                    raw = await self.sandbox.files.read(node.path, format="text")
                    text = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
                    total_bytes += len(text.encode("utf-8"))
                    contents[node.path] = {"content": text, "language": detect_language(node.path)}
                except Exception:
                    pass

        tree = await self.list_files_recursive(path, max_depth=max_depth)
        await _collect(tree, current_depth=0)
        return tree, contents

    @e2b_exception_handler
    async def read_file_content(
        self,
        file_path: str,
        *,
        skip_metadata_check: bool = False,
    ) -> FileContentResponse:
        """Read file content with language detection."""
        await self._ensure_sandbox_connection()

        mime_type = guess_mime_type(file_path)
        entry_size: int | None = None

        if not skip_metadata_check:
            parent = os.path.dirname(file_path)
            basename = os.path.basename(file_path)
            try:
                entries = await self.sandbox.files.list(parent)
                for entry in entries:
                    if entry.name == basename:
                        if _is_dir_entry(entry):
                            raise SandboxOperationError(
                                "read_file_content", f"path '{file_path}' is a directory"
                            )
                        if hasattr(entry, "size") and entry.size:
                            entry_size = int(entry.size)
                        break
            except SandboxOperationError:
                raise
            except Exception:
                pass

        if is_image_file_path(file_path, include_svg=False):
            return FileContentResponse(
                path=file_path, file_kind="image", mime_type=mime_type or "application/octet-stream"
            )

        if entry_size is not None and entry_size > MAX_FILE_CONTENT_SIZE:
            return FileContentResponse(
                path=file_path,
                file_kind="binary",
                mime_type=mime_type,
                message="File too big. Open VS Code to view.",
                too_big=True,
            )

        if is_binary_file_path(file_path):
            return FileContentResponse(
                path=file_path,
                file_kind="binary",
                mime_type=mime_type,
                message="Binary preview is not supported here. Open VS Code to view.",
            )

        content = await self.sandbox.files.read(file_path, format="text")
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")

        if len(content) > MAX_FILE_CONTENT_SIZE:
            return FileContentResponse(
                path=file_path,
                file_kind="binary",
                mime_type=mime_type,
                message="File too big. Open VS Code to view.",
                too_big=True,
            )

        language = detect_language(file_path)
        return FileContentResponse(
            path=file_path, content=content, language=language, mime_type=mime_type
        )

    async def watch_dir(
        self,
        path: str,
        on_event: Any,
        on_exit: Any,
        *,
        timeout: int = 0,
        recursive: bool = True,
    ) -> Any:
        """Start an E2B filesystem watcher on *path*."""
        await self._ensure_sandbox_connection()
        return await self.sandbox.files.watch_dir(
            path,
            on_event=on_event,
            on_exit=on_exit,
            timeout=timeout,
            recursive=recursive,
        )

    # ── Networking ────────────────────────────────────────────────────────

    async def expose_port(self, port: int) -> str:
        await self._ensure_sandbox_connection()
        host = self.sandbox.get_host(port)
        return f"https://{host}"

    async def get_host(self) -> str:
        return f"{self.provider_sandbox_id}.{self.sandbox.connection_config.domain}"

    def get_mcp_client(self, sandbox_url: str) -> Client:
        mcp_url = sandbox_url + "/mcp/"
        if self.mcp_client is None:
            self.mcp_client = Client(mcp_url, timeout=self._config.mcp.timeout)
        return self.mcp_client

    # ── Internal helpers ──────────────────────────────────────────────────

    async def _ensure_sandbox_connection(self) -> None:
        if self.sandbox is None:
            raise SandboxNotInitializedError(
                f"Sandbox not yet initialized provider = {self.provider}, "
                f"provider_id = {self.provider_sandbox_id}"
            )

        sandbox_info = await AsyncSandbox.get_info(
            sandbox_id=self.provider_sandbox_id,
            api_key=self._config.sandbox.e2b_api_key,
            domain=self._config.sandbox.e2b_domain,
        )
        timeout_buffer = timedelta(seconds=60)
        should_connect = (sandbox_info.state == SandboxState.PAUSED) or (
            sandbox_info.end_at < datetime.now(timezone.utc) - timeout_buffer
        )
        if should_connect:
            self.sandbox = await AsyncSandbox.connect(
                self.provider_sandbox_id,
                api_key=self._config.sandbox.e2b_api_key,
                timeout=self._config.sandbox.extended_timeout_seconds,
                domain=self._config.sandbox.e2b_domain,
            )
            self.status = SandboxStatus.RUNNING

    @staticmethod
    def _to_sandbox_status(sandbox_state: SandboxState) -> SandboxStatus:
        if sandbox_state.RUNNING:
            return SandboxStatus.RUNNING
        if sandbox_state.PAUSED:
            return SandboxStatus.PAUSED
        raise ValueError(f"Unrecognized sandbox status: {sandbox_state}")
