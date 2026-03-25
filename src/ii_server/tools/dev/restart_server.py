"""Tool for restarting development servers."""

import os
import signal
import subprocess
from typing import Any, Dict, List

from ii_server.core.models import ServerConfig
from ii_server.core.tool_server_config import get_tool_server_config
from ii_server.core.workspace import FileSystemValidationError, WorkspaceManager
from ii_server.logger import get_logger
from ii_server.tools.base import BaseTool, ToolResult
from ii_server.tools.dev.template_processor.base_processor import BaseProcessor
from ii_server.tools.shell.terminal_manager import (
    BaseShellManager,
    ShellError,
    ShellSessionNotFoundError,
)

logger = get_logger(__name__)


NAME = "restart_fullstack_servers"
DISPLAY_NAME = "Restart dev servers"
DESCRIPTION = (
    "Stops and restarts development servers using metadata recorded during project initialization."
)

INPUT_SCHEMA = {"type": "object", "properties": {}, "required": []}


class RestartServerTool(BaseTool):
    """Tool to restart development servers."""

    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    def __init__(
        self,
        terminal_manager: BaseShellManager,
        workspace_manager: WorkspaceManager,
    ) -> None:
        super().__init__()
        self.terminal_manager = terminal_manager
        self.workspace_manager = workspace_manager

    def _kill_port(self, port: int) -> List[int]:
        """Kill processes listening on the given port; return killed PIDs."""
        pids: List[int] = []
        try:
            proc = subprocess.run(
                ["lsof", "-t", f"-i:{port}"],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in proc.stdout.strip().splitlines():
                if not line.strip().isdigit():
                    continue
                pid = int(line.strip())
                try:
                    os.kill(pid, signal.SIGTERM)
                    pids.append(pid)
                except OSError:
                    continue
        except FileNotFoundError:
            pass

        if not pids:
            try:
                subprocess.run(
                    ["fuser", "-k", f"{port}/tcp"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except FileNotFoundError:
                pass

        if pids:
            logger.info("Killed %s process(es) on port %s: %s", len(pids), port, pids)

        return pids

    def _stop_session(self, session_name: str) -> None:
        """Stop a running session if it exists."""
        try:
            if session_name in self.terminal_manager.get_all_sessions():
                self.terminal_manager.kill_current_command(session_name)
        except (ShellError, ShellSessionNotFoundError):
            pass

    def _ensure_session(self, session_name: str, run_dir: str) -> None:
        """Ensure a session exists, creating it if necessary."""
        current_sessions = set(self.terminal_manager.get_all_sessions())
        if session_name not in current_sessions:
            self.terminal_manager.create_session(session_name, run_dir)

    def _restart_server(self, server: ServerConfig) -> Dict[str, Any]:
        """Restart a single server and return status information."""
        name = server.session
        session = server.session
        run_dir = server.run_dir
        command_template = server.command
        start_port = server.port

        if not all([session, run_dir, command_template, start_port]):
            raise ValueError(f"Missing restart metadata for {name}")

        self.workspace_manager.validate_existing_directory_path(run_dir)

        # killed = self._kill_port(start_port)
        self._stop_session(session)
        self._ensure_session(session, run_dir)

        if BaseProcessor.PORT_PLACEHOLDER in command_template:
            port = BaseProcessor._find_available_port(start_port)
            command = command_template.replace(BaseProcessor.PORT_PLACEHOLDER, str(port))
        else:
            port = start_port
            command = command_template

        server.port = port
        server.deployment_url = BaseProcessor._get_deployment_url(port)

        self.terminal_manager.run_command(
            session,
            command,
            run_dir=run_dir,
            wait_for_output=False,
        )
        session_view = self.terminal_manager.get_session_output(session)
        return {
            "name": name,
            "session": session,
            "url": server.deployment_url,
            "port": port,
            "session_output": session_view.clean_output,
        }

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Execute the restart operation."""
        config = get_tool_server_config().get_deployment_config()

        if not config or not config.servers:
            return ToolResult(
                llm_content="No deployment configuration found; run init first.",
                user_display_content="No deployment config found; run init first.",
                is_error=True,
            )

        results: List[Dict[str, Any]] = []
        errors: List[str] = []
        preview_port = config.preview_port
        preview_url = config.preview_url

        for server in config.servers:
            is_preview = server.port == config.preview_port
            try:
                entry = self._restart_server(server)
                results.append(entry)
                logger.info(
                    "Restarted server %s (session=%s, port=%s)",
                    entry.get("name"),
                    entry.get("session"),
                    entry.get("port"),
                )
                if is_preview:
                    preview_port = server.port
                    preview_url = server.deployment_url
            except (ValueError, FileSystemValidationError, ShellError) as exc:
                errors.append(f"{server.session}: {exc}")
            except Exception as exc:  # pragma: no cover - defensive
                errors.append(f"Unexpected error for {server.session}: {exc}")

        # Persist updated config
        if results:
            try:
                config.preview_port = preview_port
                if preview_url:
                    config.preview_url = preview_url
                get_tool_server_config().set_deployment_config(config)
            except Exception as exc:
                logger.warning(
                    "Server restarted but failed to persist updated metadata: %s. "
                    "Config may be stale on next restart.",
                    exc,
                )

        if not results:
            return ToolResult(
                llm_content="Failed to restart any servers: " + "; ".join(errors),
                user_display_content="Restart failed; see errors in llm_content.",
                is_error=True,
            )

        message = "Restarted servers:\n" + "\n".join(
            [
                f"- {entry['name']} ({entry.get('url') or 'unknown url'}) on port {entry['port']} via session `{entry['session']}`"
                for entry in results
            ]
        )
        if errors:
            message += "\nErrors: " + "; ".join(errors)

        # Return preview_url at top level for frontend compatibility
        result_payload = {
            "preview_url": preview_url or config.preview_url,
            "preview_port": preview_port,
            "servers": results,
        }

        return ToolResult(
            llm_content=message,
            user_display_content=result_payload,
            is_error=bool(errors),
        )

    async def execute_mcp_wrapper(self):
        """MCP wrapper for execute."""
        return await self._mcp_wrapper(tool_input={})
