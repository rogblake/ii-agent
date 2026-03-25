"""Base processor for web application templates."""

from abc import ABC, abstractmethod
from pathlib import Path
import shlex
import socket
import time
from typing import ClassVar, Dict

from typing_extensions import final

from ii_server.core.constants import DEFAULT_WORKSPACE, USER_ENV_PATH, USER_ENV_SH_PATH
from ii_server.core.models import DeploymentConfig, ServerConfig
from ii_server.logger import get_logger
from ii_server.tools.shell.terminal_manager import BaseShellManager
from .utils import get_templates_dir

logger = get_logger(__name__)


class BaseProcessor(ABC):
    """Abstract base class for template processors.

    Subclasses must implement:
        - install_dependencies(): Framework-specific dependency installation
        - get_deployment_config(): Returns the deployment configuration

    Subclasses may override:
        - apply_database_rule(): Add database integration rules (default: no-op)
    """

    template_name: ClassVar[str] = ""
    PORT_PLACEHOLDER: ClassVar[str] = "{PORT}"

    def __init__(
        self,
        project_name: str,
        project_dir: str,
        terminal_manager: BaseShellManager,
        host_url: str | None = None,
    ):
        self.project_name = project_name
        self.project_dir = project_dir
        self.terminal_manager = terminal_manager
        self.host_url = host_url
        self.project_rule: str = ""

    # -------------------------------------------------------------------------
    # Abstract methods - must be implemented by subclasses
    # -------------------------------------------------------------------------

    @abstractmethod
    def install_dependencies(self) -> None:
        """Install framework-specific dependencies."""
        ...

    @abstractmethod
    def get_deployment_config(self) -> DeploymentConfig:
        """Return the deployment configuration for this project."""
        ...

    # -------------------------------------------------------------------------
    # Optional methods - can be overridden by subclasses
    # -------------------------------------------------------------------------

    def apply_database_rule(self) -> None:
        """Apply database integration rules.

        Override in subclasses that support database integration.
        Default implementation does nothing.
        """
        pass

    # -------------------------------------------------------------------------
    # Common utility methods
    # -------------------------------------------------------------------------

    @staticmethod
    def _find_available_port(start_port: int) -> int:
        """Find an available port starting from start_port.

        Args:
            start_port: The port to start searching from.

        Returns:
            An available port number.
        """
        port = start_port
        while True:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind(("0.0.0.0", port))
                    return port
                except OSError:
                    port += 1

    def _get_deployment_url(self, port: int) -> str:
        """Generate the deployment URL for a given port.

        Args:
            port: The port number.

        Returns:
            A URL string or a message indicating the port needs to be exposed.
        """
        if self.host_url:
            return f"https://{port}-{self.host_url}"
        return f"Expose port {port} to get the public previewable deployment"

    def _resolve_server_command(self, server: ServerConfig) -> tuple[int, str]:
        """Resolve the server port and command."""
        command = server.command
        if self.PORT_PLACEHOLDER in command:
            port = self._find_available_port(server.port)
            command = command.replace(self.PORT_PLACEHOLDER, str(port))
            return port, command

        port = server.port
        return port, command

    @staticmethod
    def _wait_for_port_ready(
        port: int,
        session_name: str,
        timeout: float = 10.0,
        poll_interval: float = 0.2,
    ) -> None:
        """Wait until a TCP port is accepting connections or time out."""
        deadline = time.monotonic() + timeout
        last_error: OSError | None = None
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    return
            except OSError as exc:
                last_error = exc
                time.sleep(poll_interval)
        raise TimeoutError(
            f"Server session '{session_name}' did not become ready on port {port} "
            f"within {timeout:.0f} seconds."
        ) from last_error

    def _ensure_session(
        self, session_name: str, default_dir: str | None = None
    ) -> None:
        """Ensure a terminal session exists, creating it if necessary.

        Args:
            session_name: Name of the session to ensure.
            default_dir: Directory for the session if created.
        """
        if session_name not in self.terminal_manager.get_all_sessions():
            run_dir = default_dir or DEFAULT_WORKSPACE
            self.terminal_manager.create_session(session_name, run_dir)

    def _load_rule(self, rule_name: str) -> str:
        """Load a rule template from the rules directory.

        Args:
            rule_name: Name of the rule file (without .md extension).

        Returns:
            The content of the rule file.

        Raises:
            FileNotFoundError: If the rule file doesn't exist.
        """
        rules_dir = Path(__file__).parent / "rules"
        rule_file = rules_dir / f"{rule_name}.md"
        if rule_file.exists():
            return rule_file.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Rule file not found: {rule_file}")

    # -------------------------------------------------------------------------
    # Server management
    # -------------------------------------------------------------------------

    def start_server(
        self, servers_config: list[ServerConfig] | None = None
    ) -> None:
        """Start the development server(s).

        Args:
            servers_config: Optional list of server configs. If not provided,
                           uses the deployment config.
        """
        servers = servers_config or self.get_deployment_config().servers
        current_sessions = set(self.terminal_manager.get_all_sessions())

        for server in servers:
            if server.session not in current_sessions:
                self.terminal_manager.create_session(server.session, server.run_dir)

            port, command = self._resolve_server_command(server)
            server.port = port
            server.deployment_url = self._get_deployment_url(port)

            self.terminal_manager.run_command(
                server.session,
                command,
                run_dir=server.run_dir,
                wait_for_output=False,
            )
            self._wait_for_port_ready(server.port, server.session)

        self._log_server_output(servers)

    def _log_server_output(self, servers: list[ServerConfig]) -> None:
        """Log the current output from all server sessions."""
        output_parts = []
        for server in servers:
            session_output = self.terminal_manager.get_session_output(server.session)
            output_parts.append(
                f"Current view of {server.session} server\n{session_output.clean_output}"
            )
        logger.info("\n".join(output_parts))

    # -------------------------------------------------------------------------
    # Final methods - not meant to be overridden
    # -------------------------------------------------------------------------

    @final
    def write_to_env(self, envs: Dict[str, str]) -> None:
        """Write environment variables to .env files.

        Creates three files:
        - Project .env file
        - /app/.user_env (key=value format)
        - /app/.user_env.sh (export format for shell sourcing)
        """
        if not envs:
            return

        env_items = sorted(
            (str(k), "" if v is None else str(v)) for k, v in envs.items()
        )

        def write_file(path: Path, lines: list[str]) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Key=value format
        kv_pairs = [f"{key}={value}" for key, value in env_items]
        project_env_path = Path(self.project_dir) / ".env"
        write_file(project_env_path, kv_pairs)
        write_file(Path(USER_ENV_PATH), kv_pairs)

        # Shell export format
        export_lines = [
            f"export {key}={shlex.quote(value)}" for key, value in env_items
        ]
        write_file(Path(USER_ENV_SH_PATH), export_lines)

    @final
    def copy_project_template(self) -> None:
        """Copy the template files to the project directory."""
        self._ensure_session("system", DEFAULT_WORKSPACE)
        template_dir = get_templates_dir() / self.template_name
        if not template_dir.is_dir():
            raise FileNotFoundError(f"Template not found: {template_dir}")
        self.terminal_manager.run_command(
            "system",
            f"cp -rf {shlex.quote(str(template_dir))} {shlex.quote(self.project_dir)}",
            wait_for_output=True,
        )

    @final
    def start_up_project(
        self,
        servers_config: list[ServerConfig] | None = None,
        envs: Dict[str, str] | None = None,
    ) -> None:
        """Full project startup sequence.

        1. Copy template files
        2. Write environment variables
        3. Install dependencies
        4. Start servers
        """
        try:
            self.copy_project_template()
            if envs:
                self.write_to_env(envs)
            self.install_dependencies()
            self.start_server(servers_config)
        except Exception:
            logger.exception("Failed to start up project at %s", self.project_dir)
            raise

    @final
    def get_project_rule(self) -> str:
        """Get the project rules/instructions."""
        if not self.project_rule:
            raise ValueError("Project rule is not set")
        return self.project_rule

    @final
    def deployment_rules(self) -> str:
        """Alias for get_project_rule()."""
        return self.get_project_rule()
