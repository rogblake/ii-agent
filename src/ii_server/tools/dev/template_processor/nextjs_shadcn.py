"""Next.js + shadcn/ui template processor."""

from ii_server.core.constants import DEFAULT_NEXTJS_PORT
from ii_server.logger import get_logger
from ii_server.tools.dev.template_processor.base_processor import (
    BaseProcessor,
    DeploymentConfig,
    ServerConfig,
)
from ii_server.tools.dev.template_processor.registry import WebProcessorRegistry
from ii_server.tools.shell.terminal_manager import BaseShellManager

logger = get_logger(__name__)


@WebProcessorRegistry.register("nextjs-shadcn")
class NextShadcnProcessor(BaseProcessor):
    """Processor for Next.js + shadcn/ui template."""

    template_name = "nextjs-shadcn"
    default_port = DEFAULT_NEXTJS_PORT

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
        rule_template = self._load_rule("nextjs_deployment")
        self.project_rule = rule_template.format(project_path=project_dir)
        self._database_rule_applied = False

    def apply_database_rule(self) -> None:
        """Append PostgreSQL integration steps when database support is requested."""
        if self._database_rule_applied:
            return

        database_rule = self._load_rule("nextjs_database")
        self.project_rule = f"{self.project_rule.rstrip()}\n\n{database_rule}\n"
        self._database_rule_applied = True

    def install_dependencies(self) -> None:
        """Install Next.js dependencies using bun."""
        self._ensure_session("system")
        self.terminal_manager.run_command(
            "system",
            "bun install",
            run_dir=self.project_dir,
            wait_for_output=True,
        )

    def get_deployment_config(self) -> DeploymentConfig:
        """Return deployment configuration for Next.js project."""
        port = self.default_port
        server_config = ServerConfig(
            deployment_url=self._get_deployment_url(port),
            port=port,
            command=f"PORT={self.PORT_PLACEHOLDER} bun run dev",
            run_dir=self.project_dir,
            session="fullstack",
        )
        return DeploymentConfig(
            preview_url=server_config.deployment_url,
            preview_port=port,
            project_name=self.project_name,
            framework=self.template_name,
            directory=self.project_dir,
            servers=[server_config],
        )
