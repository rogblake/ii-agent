import os

from typing import Any, Optional

from ii_server.core.tool_server_config import get_tool_server_config
from ii_server.core.workspace import WorkspaceManager
from ii_server.logger import get_logger
from ii_server.tools.base import BaseTool, ToolResult
from ii_server.tools.dev.template_processor.registry import WebProcessorRegistry
from ii_server.tools.shell.terminal_manager import BaseShellManager

logger = get_logger(__name__)

# Name
NAME = "fullstack_project_init"
DISPLAY_NAME = "Initialize application template"

# Description
DESCRIPTION = """Initialize a fullstack application from the packaged templates.

Set `database=true` to scaffold the database-aware variant of the template.
Optionally provide `database_connection` to have `DATABASE_URL` written into
the generated `.env` file during setup.
"""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "project_name": {
            "type": "string",
            "description": "A name for your project (lowercase, no spaces, use hyphens if needed). Example: `my-app`",
        },
        "framework": {
            "type": "string",
            "description": "The framework to use for the project",
            "enum": ["nextjs-shadcn", "react-shadcn-python"],
        },
        "database": {
            "type": "boolean",
            "description": "Whether to scaffold the database-enabled variant of the template.",
            "default": False,
        },
        "database_connection": {
            "type": "string",
            "description": "Optional database connection string to write into the generated project environment.",
            "default": None,
        },
        "host_url": {
            "type": "string",
            "description": "Optional sandbox host suffix used to build preview URLs like https://3000-<host_url>.",
            "default": None,
        },
    },
    "required": ["project_name", "framework"],
}


class FullStackInitTool(BaseTool):
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

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        project_name = tool_input["project_name"]
        framework = tool_input["framework"]
        database = tool_input.get("database", False)
        database_connection = tool_input.get("database_connection")
        host_url = tool_input.get("host_url")
        existing_config = get_tool_server_config().get_deployment_config()
        if existing_config:
            return ToolResult(
                llm_content="A project is already initialized in this workspace; only one project can be active.",
                user_display_content="A project is already initialized.",
                is_error=True,
            )

        project_dir = os.path.join(
            self.workspace_manager.get_workspace_path(),
            project_name,
        )
        if (
            os.path.isabs(project_name)
            or ".." in project_name
            or os.path.sep in project_name
        ):
            message = (
                f"Project name `{project_name}` is invalid; use a simple folder "
                "name without path separators."
            )
            return ToolResult(
                llm_content=message,
                user_display_content=message,
                is_error=True,
            )
        if not self.workspace_manager.validate_boundary(project_dir):
            message = (
                f"Project directory `{project_dir}` must stay within the workspace "
                "boundary."
            )
            return ToolResult(
                llm_content=message,
                user_display_content=message,
                is_error=True,
            )
        if os.path.exists(project_dir):
            return ToolResult(
                llm_content=(
                    f"Project directory {project_dir} already exists, please choose "
                    "a different project name"
                ),
                user_display_content=(
                    "Project directory already exists, please choose a different "
                    "project name"
                ),
                is_error=True,
            )

        envs = None
        database_payload = None
        if database and database_connection:
            envs = {"DATABASE_URL": database_connection}
            database_payload = {"connection_string": database_connection}

        processor = WebProcessorRegistry.create(
            framework,
            project_name,
            project_dir,
            self.terminal_manager,
            host_url=host_url,
        )

        if database:
            processor.apply_database_rule()

        deployment_config = processor.get_deployment_config()
        preview_session = None
        for server in deployment_config.servers:
            if server.port == deployment_config.preview_port:
                preview_session = server.session
                break
        if not preview_session and deployment_config.servers:
            preview_session = deployment_config.servers[0].session
        try:
            processor.start_up_project(
                deployment_config.servers,
                envs=envs,
            )
        except Exception as exc:
            logger.exception("Failed to start up project", exc_info=True)
            return ToolResult(
                llm_content=f"Failed to start up project in {project_dir}: {exc}",
                user_display_content=(
                    f"Failed to start up project in {project_dir}: {exc}"
                ),
                is_error=True,
            )

        preview_port = deployment_config.preview_port
        if preview_session:
            preview_server = next(
                (
                    server
                    for server in deployment_config.servers
                    if server.session == preview_session
                ),
                None,
            )
            if preview_server:
                preview_port = preview_server.port
                deployment_config.preview_port = preview_port
                deployment_config.preview_url = preview_server.deployment_url

        try:
            get_tool_server_config().set_deployment_config(deployment_config)
        except Exception as exc:
            return ToolResult(
                llm_content=(
                    "Project initialized but failed to persist deployment metadata "
                    f"to /app/.tool_server_config.json: {exc}"
                ),
                user_display_content=(
                    "Project initialized but failed to persist deployment metadata: "
                    f"{exc}"
                ),
                is_error=True,
            )

        result_payload = deployment_config.model_dump()
        result_payload["preview_port"] = preview_port
        result_payload["preview_url"] = deployment_config.preview_url
        if database_payload:
            result_payload["database"] = database_payload

        logger.info(
            "Initialized project %s with framework %s at %s (port %s)",
            project_name,
            framework,
            project_dir,
            preview_port,
        )

        db_note = ""
        if database_connection:
            db_note = (
                "Database option enabled: connection string is set in .env. "
                "Follow the appended PostgreSQL guide to scaffold Prisma and auth "
                "before relying on DB-backed flows.\n\n"
            )
        elif database:
            db_note = (
                "Database option enabled, but no database connection string was "
                "provided. Add `DATABASE_URL` before using DB-backed flows.\n\n"
            )

        return ToolResult(
            llm_content=(
                f"{processor.deployment_rules()}\n"
                f"The project **{project_name}** has been successfully initialized "
                "with the following configuration:\n\n"
                f"- **Workspace Directory:** "
                f"`{self.workspace_manager.get_workspace_path()}`\n"
                f"- **Project Path:** `{project_dir}`\n"
                f"- **Dev Server:** Running at `{deployment_config.preview_url}`\n"
                f"- **Port:** {preview_port}\n\n"
                f"{db_note}"
            ),
            user_display_content=result_payload,
            is_error=False,
        )

    async def execute_mcp_wrapper(
        self,
        project_name: str,
        framework: str,
        database: Optional[bool] = False,
        database_connection: Optional[str] = None,
        host_url: Optional[str] = None,
    ):
        return await self._mcp_wrapper(
            tool_input={
                "project_name": project_name,
                "framework": framework,
                "database": database,
                "database_connection": database_connection,
                "host_url": host_url,
            }
        )
