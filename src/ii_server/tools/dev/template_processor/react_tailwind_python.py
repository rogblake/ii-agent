"""React + Tailwind CSS + Python FastAPI template processor."""

import os

from ii_server.core.constants import DEFAULT_BACKEND_PORT, DEFAULT_FRONTEND_PORT
from ii_server.logger import get_logger
from ii_server.tools.dev.template_processor.base_processor import (
    BaseProcessor,
    DeploymentConfig,
    ServerConfig,
)
from ii_server.tools.dev.template_processor.registry import WebProcessorRegistry
from ii_server.tools.shell.terminal_manager import BaseShellManager

logger = get_logger(__name__)


@WebProcessorRegistry.register("react-shadcn-python")
class ReactShadcnPythonProcessor(BaseProcessor):
    """Processor for React + shadcn/ui + Python FastAPI template."""

    template_name = "react-shadcn-python"
    default_backend_port = DEFAULT_BACKEND_PORT
    default_frontend_port = DEFAULT_FRONTEND_PORT

    def __init__(
        self,
        project_name: str,
        project_dir: str,
        terminal_manager: BaseShellManager,
        host_url: str | None = None,
    ):
        super().__init__(
            project_name=project_name,
            project_dir=project_dir,
            terminal_manager=terminal_manager,
            host_url=host_url,
        )
        # Load deployment rule from external file
        rule_template = self._load_rule("react_python_deployment")
        self.project_rule = rule_template.format(project_path=project_dir)

    def install_dependencies(self) -> None:
        """Install frontend (bun) and backend (pip) dependencies."""
        frontend_dir = os.path.join(self.project_dir, "frontend")
        backend_dir = os.path.join(self.project_dir, "backend")

        self._ensure_session("system")

        self.terminal_manager.run_command(
            "system",
            "bun install",
            run_dir=frontend_dir,
            wait_for_output=True,
        )

        self.terminal_manager.run_command(
            "system",
            "pip install -r requirements.txt",
            run_dir=backend_dir,
            wait_for_output=True,
        )

    def get_deployment_config(self) -> DeploymentConfig:
        """Return deployment configuration for React + Python project."""
        backend_port = self.default_backend_port
        frontend_port = self.default_frontend_port

        frontend_dir = os.path.join(self.project_dir, "frontend")
        backend_dir = os.path.join(self.project_dir, "backend")

        servers = [
            ServerConfig(
                deployment_url=self._get_deployment_url(backend_port),
                port=backend_port,
                command=(
                    "uvicorn src.main:app --host 0.0.0.0 "
                    f"--port {self.PORT_PLACEHOLDER} --reload"
                ),
                run_dir=backend_dir,
                session="backend",
            ),
            ServerConfig(
                deployment_url=self._get_deployment_url(frontend_port),
                port=frontend_port,
                command=f"bun run dev -- --host --port {self.PORT_PLACEHOLDER}",
                run_dir=frontend_dir,
                session="frontend",
            ),
        ]

        # Primary server is the frontend
        primary_server = servers[1]

        return DeploymentConfig(
            preview_url=primary_server.deployment_url,
            preview_port=primary_server.port,
            project_name=self.project_name,
            framework=self.template_name,
            directory=self.project_dir,
            servers=servers,
        )
