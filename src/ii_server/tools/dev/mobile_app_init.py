"""Mobile app initialization tool for Expo projects (Internal)."""

import os
import asyncio
from typing import Any, Dict

from ii_server.tools.base import BaseTool, ToolResult
from ii_server.core.workspace import WorkspaceManager
from ii_server.tools.shell.terminal_manager import BaseShellManager
from ii_server.core.tool_server_config import get_tool_server_config
from ii_server.tools.expo_server_startup import start_expo_dev_server
from ii_server.logger import get_logger

logger = get_logger(__name__)

# Name
NAME = "mobile_app_init_internal"
DISPLAY_NAME = "Initialize Mobile App (Internal)"

# Description - kept minimal since this is an internal tool
DESCRIPTION = """Internal tool for initializing Expo mobile app projects. This message should not be read by LLM."""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "project_name": {
            "type": "string",
            "description": "Name for the mobile app project (lowercase, no spaces, use hyphens if needed). Example: `my-app`, `todo-app`",
        },
        "template": {
            "type": "string",
            "description": "Expo template to use",
            "enum": ["tabs", "blank", "blank-typescript"],
            "default": "tabs",
        },
        "example": {
            "type": "string",
            "description": "Expo example to use instead of template. When provided, creates project from an official Expo example (e.g., 'with-reanimated' for games/animations). See https://github.com/expo/examples for available examples.",
        },
        "with_tailwind": {
            "type": "boolean",
            "description": "Whether to set up NativeWind/Tailwind CSS styling",
            "default": True,
        },
    },
    "required": ["project_name"],
}


class MobileAppInitToolInternal(BaseTool):
    """Internal tool for initializing Expo mobile app projects."""

    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    # Default ports for Expo
    EXPO_WEB_PORT = 8081
    EXPO_METRO_PORT = 8081

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
        template = tool_input.get("template", "tabs")
        example = tool_input.get("example")
        with_tailwind = tool_input.get("with_tailwind", True)

        # Check if project already exists
        existing_config = get_tool_server_config().get_mobile_app_config()
        if existing_config:
            return ToolResult(
                llm_content="A mobile app project is already initialized in this workspace; only one project can be active.",
                user_display_content="A mobile app project is already initialized.",
                is_error=True,
            )

        # Validate project name
        workspace_path = str(self.workspace_manager.get_workspace_path())
        project_dir = os.path.join(workspace_path, project_name)

        if os.path.isabs(project_name) or ".." in project_name or os.path.sep in project_name:
            message = f"Project name `{project_name}` is invalid; use a simple folder name without path separators."
            return ToolResult(
                llm_content=message,
                user_display_content=message,
                is_error=True,
            )

        if not self.workspace_manager.validate_boundary(project_dir):
            message = f"Project directory `{project_dir}` must stay within the workspace boundary."
            return ToolResult(
                llm_content=message,
                user_display_content=message,
                is_error=True,
            )

        if os.path.exists(project_dir):
            return ToolResult(
                llm_content=f"Project directory {project_dir} already exists, please choose a different project name",
                user_display_content="Project directory already exists, please choose a different project name",
                is_error=True,
            )

        try:
            # Ensure terminal session exists
            self._ensure_session("mobile", workspace_path)

            # Step 1: Create Expo project
            create_result = await self._create_expo_project(project_name, template, example)
            if not create_result["success"]:
                return ToolResult(
                    llm_content=f"Failed to create Expo project: {create_result['error']}",
                    user_display_content=f"Failed to create Expo project: {create_result['error']}",
                    is_error=True,
                )

            # Step 2: Install dependencies
            install_result = await self._install_dependencies(project_dir, with_tailwind)
            if not install_result["success"]:
                return ToolResult(
                    llm_content=f"Failed to install dependencies: {install_result['error']}",
                    user_display_content=f"Failed to install dependencies: {install_result['error']}",
                    is_error=True,
                )

            # Step 3: Save configuration BEFORE starting server
            # This allows restart_mobile_server to work even if initial start fails
            mobile_app_config = {
                "project_name": project_name,
                "project_dir": project_dir,
                "template": template,
                "with_tailwind": with_tailwind,
                "web_port": self.EXPO_WEB_PORT,
                "tunnel_url": None,
                "qr_code_value": None,
                "web_url": None,
            }
            get_tool_server_config().set_mobile_app_config(mobile_app_config)

            # Step 4: Start Expo with tunnel mode
            start_result = await self._start_expo_server(project_dir)
            if not start_result["success"]:
                error_msg = start_result['error']
                return ToolResult(
                    llm_content=(
                        f"Failed to start Expo server: {error_msg}\n\n"
                        f"**IMPORTANT**: The project has been created at `{project_dir}`. "
                        f"After installing the required packages, you MUST call `restart_mobile_server` tool to start the server."
                    ),
                    user_display_content=f"Failed to start Expo server: {error_msg}",
                    is_error=True,
                )

            # Step 5: Update configuration with server URLs
            tunnel_url = start_result.get("tunnel_url")
            qr_code_value = start_result.get("qr_code_value")
            web_url = start_result.get("web_url")
            startup_mode = start_result.get("startup_mode", "tunnel")
            startup_warning = start_result.get("warning")

            mobile_app_config["tunnel_url"] = tunnel_url
            mobile_app_config["qr_code_value"] = qr_code_value
            mobile_app_config["web_url"] = web_url
            mobile_app_config["startup_mode"] = startup_mode

            get_tool_server_config().set_mobile_app_config(mobile_app_config)

            # Build response
            result_payload = {
                "project_name": project_name,
                "project_path": project_dir,
                "template": template,
                "web_port": self.EXPO_WEB_PORT,
                "tunnel_url": tunnel_url,
                "qr_code_value": qr_code_value,
                "web_url": web_url,
                "with_tailwind": with_tailwind,
                "startup_mode": startup_mode,
            }
            if startup_warning:
                result_payload["warning"] = startup_warning

            qr_instructions = ""
            if tunnel_url:
                qr_instructions = f"\n- **Tunnel URL (for QR code):** `{tunnel_url}`\n- **Web URL:** `{web_url or 'http://localhost:8081'}`"
            elif qr_code_value:
                qr_instructions = f"\n- **LAN QR URL:** `{qr_code_value}`\n- **Web URL:** `{web_url or 'http://localhost:8081'}`"
            elif web_url:
                qr_instructions = f"\n- **Web URL:** `{web_url}`"

            startup_notes = ""
            if startup_warning:
                startup_notes = f"\n\n### Startup Note:\n{startup_warning}"

            return ToolResult(
                llm_content=(
                    f"## Mobile App Initialized Successfully!\n\n"
                    f"The Expo project **{project_name}** has been created with the following configuration:\n\n"
                    f"- **Project Path:** `{project_dir}`\n"
                    f"- **Template:** {template}\n"
                    f"- **Web Port:** {self.EXPO_WEB_PORT} (use register_deployment tool to get public URL)\n"
                    f"- **Tailwind/NativeWind:** {'Enabled' if with_tailwind else 'Disabled'}"
                    f"{qr_instructions}"
                    f"{startup_notes}\n\n"
                    f"### Next Steps:\n"
                    f"1. Use `register_deployment` tool with port {self.EXPO_WEB_PORT} to get the web preview URL\n"
                    f"2. Scan the QR code with Expo Go app (iOS/Android) to test on device\n"
                    f"3. Edit files in `{project_dir}/app/` to modify the app\n"
                    f"4. Use Expo skills for guidance on building features\n"
                ),
                user_display_content=result_payload,
                is_error=False,
            )

        except Exception as e:
            logger.exception("Failed to initialize mobile app", exc_info=True)
            return ToolResult(
                llm_content=f"Failed to initialize mobile app: {e}",
                user_display_content=f"Failed to initialize mobile app: {e}",
                is_error=True,
            )

    def _ensure_session(self, session_name: str, default_dir: str) -> None:
        """Ensure a terminal session exists."""
        if session_name not in self.terminal_manager.get_all_sessions():
            self.terminal_manager.create_session(session_name, default_dir)

    async def _create_expo_project(self, project_name: str, template: str, example: str | None = None) -> Dict[str, Any]:
        """Create a new Expo project."""
        try:
            # If example is provided, use --example flag instead of template
            if example:
                command = f"bunx create-expo-app@latest {project_name} --example {example} --no-install"
            else:
                # Map template to Expo template flag
                template_flag = "--template default"
                if template == "tabs":
                    template_flag = "--template tabs"
                elif template == "blank-typescript":
                    template_flag = "--template blank-typescript"
                sdk_version = "@sdk-54"

                command = f"bunx create-expo-app@latest {project_name} {template_flag}{sdk_version} --no-install"

            self.terminal_manager.run_command(
                "mobile",
                command,
                run_dir=str(self.workspace_manager.get_workspace_path()),
                wait_for_output=True,
            )

            # Give it a moment to complete
            await asyncio.sleep(2)

            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _install_dependencies(self, project_dir: str, with_tailwind: bool) -> Dict[str, Any]:
        """Install project dependencies."""
        try:
            # Install base dependencies
            self.terminal_manager.run_command(
                "mobile",
                "bun install",
                run_dir=project_dir,
                wait_for_output=True,
            )

            # Wait for installation to complete
            await asyncio.sleep(10)

            # Install expo plugins that are commonly referenced in templates but may not be installed
            # expo-splash-screen is needed by the tabs template
            self.terminal_manager.run_command(
                "mobile",
                "bunx expo install expo-splash-screen expo-status-bar expo-system-ui",
                run_dir=project_dir,
                wait_for_output=True,
            )
            await asyncio.sleep(10)

            # Install @expo/ngrok for tunnel mode support
            self.terminal_manager.run_command(
                "mobile",
                "bun add -d @expo/ngrok",
                run_dir=project_dir,
                wait_for_output=True,
            )
            await asyncio.sleep(5)

            # Install react-dom and react-native-web for web support (required for --web flag)
            self.terminal_manager.run_command(
                "mobile",
                "bunx expo install react-dom react-native-web",
                run_dir=project_dir,
                wait_for_output=True,
            )
            await asyncio.sleep(5)

            if with_tailwind:
                # Install NativeWind and Tailwind dependencies
                tailwind_deps = (
                    "tailwindcss@^4 nativewind@5.0.0-preview.2 "
                    "react-native-css@0.0.0-nightly.5ce6396 "
                    "@tailwindcss/postcss tailwind-merge clsx"
                )
                self.terminal_manager.run_command(
                    "mobile",
                    f"bunx expo install {tailwind_deps}",
                    run_dir=project_dir,
                    wait_for_output=True,
                )
                await asyncio.sleep(10)

            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _start_expo_server(self, project_dir: str) -> Dict[str, Any]:
        """Start Expo development server with tunnel mode."""
        return await start_expo_dev_server(
            terminal_manager=self.terminal_manager,
            project_dir=project_dir,
            logger=logger,
            session_name="mobile",
            fallback_to_lan=True,
        )

    async def execute_mcp_wrapper(
        self,
        project_name: str,
        template: str = "tabs",
        example: str | None = None,
        with_tailwind: bool = True,
    ):
        """MCP wrapper for the tool."""
        tool_input = {
            "project_name": project_name,
            "template": template,
            "with_tailwind": with_tailwind,
        }
        if example:
            tool_input["example"] = example
        return await self._mcp_wrapper(tool_input=tool_input)
