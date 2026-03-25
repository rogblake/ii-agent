"""Tool for restarting mobile app development server."""

import asyncio
from typing import Any, Dict

from ii_server.tools.base import BaseTool, ToolResult
from ii_server.core.workspace import WorkspaceManager
from ii_server.tools.shell.terminal_manager import BaseShellManager, ShellError, ShellSessionNotFoundError
from ii_server.core.tool_server_config import get_tool_server_config
from ii_server.tools.expo_server_startup import start_expo_dev_server
from ii_server.logger import get_logger

logger = get_logger(__name__)

# Name - same as v1 wrapper for direct MCP passthrough
NAME = "restart_mobile_server"
DISPLAY_NAME = "Restart Mobile App Server"

# Description
DESCRIPTION = """Restarts the Expo mobile app development server, generating new tunnel URLs for device testing."""

# Input schema
INPUT_SCHEMA = {"type": "object", "properties": {}, "required": []}


class RestartMobileServerToolInternal(BaseTool):
    """Internal tool for restarting the Expo mobile app development server."""

    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    # Default ports for Expo
    EXPO_WEB_PORT = 8081

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
        # Get existing mobile app config
        mobile_app_config = get_tool_server_config().get_mobile_app_config()

        if not mobile_app_config:
            return ToolResult(
                llm_content="No mobile app project is initialized. Please use `mobile_app_init` tool first to create a mobile app project.",
                user_display_content="No mobile app project found. Initialize one first.",
                is_error=True,
            )

        project_dir = mobile_app_config.get("project_dir")
        project_name = mobile_app_config.get("project_name")

        if not project_dir:
            return ToolResult(
                llm_content="Mobile app configuration is missing project directory.",
                user_display_content="Invalid mobile app configuration.",
                is_error=True,
            )

        try:
            # Step 1: Stop the existing mobile session
            self._stop_session("mobile")

            # Give it a moment to clean up
            await asyncio.sleep(1)

            # Step 2: Ensure the terminal session exists
            workspace_path = str(self.workspace_manager.get_workspace_path())
            self._ensure_session("mobile", workspace_path)

            # Step 3: Restart Expo server with tunnel mode
            start_result = await self._start_expo_server(project_dir)

            if not start_result["success"]:
                return ToolResult(
                    llm_content=f"Failed to restart Expo server: {start_result.get('error', 'Unknown error')}",
                    user_display_content=f"Failed to restart Expo server: {start_result.get('error', 'Unknown error')}",
                    is_error=True,
                )

            # Step 4: Update the configuration with new URLs
            tunnel_url = start_result.get("tunnel_url")
            qr_code_value = start_result.get("qr_code_value")
            web_url = start_result.get("web_url")
            startup_mode = start_result.get("startup_mode", "tunnel")
            startup_warning = start_result.get("warning")

            # Update mobile app config
            mobile_app_config["tunnel_url"] = tunnel_url
            mobile_app_config["qr_code_value"] = qr_code_value
            mobile_app_config["web_url"] = web_url
            mobile_app_config["startup_mode"] = startup_mode

            get_tool_server_config().set_mobile_app_config(mobile_app_config)

            # Build response
            result_payload = {
                "project_name": project_name,
                "project_path": project_dir,
                "web_port": self.EXPO_WEB_PORT,
                "tunnel_url": tunnel_url,
                "qr_code_value": qr_code_value,
                "web_url": web_url,
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
                    f"## Mobile App Server Restarted Successfully!\n\n"
                    f"The Expo development server for **{project_name}** has been restarted:\n\n"
                    f"- **Project Path:** `{project_dir}`\n"
                    f"- **Web Port:** {self.EXPO_WEB_PORT}"
                    f"{qr_instructions}"
                    f"{startup_notes}\n\n"
                    f"### Next Steps:\n"
                    f"1. The QR code has been updated - scan with Expo Go to test on device\n"
                    f"2. The web preview will refresh automatically\n"
                ),
                user_display_content=result_payload,
                is_error=False,
            )

        except Exception as e:
            logger.exception("Failed to restart mobile app server", exc_info=True)
            return ToolResult(
                llm_content=f"Failed to restart mobile app server: {e}",
                user_display_content=f"Failed to restart mobile app server: {e}",
                is_error=True,
            )

    def _stop_session(self, session_name: str) -> None:
        """Stop a running session if it exists."""
        try:
            if session_name in self.terminal_manager.get_all_sessions():
                self.terminal_manager.kill_current_command(session_name)
        except (ShellError, ShellSessionNotFoundError):
            pass

    def _ensure_session(self, session_name: str, default_dir: str) -> None:
        """Ensure a terminal session exists."""
        if session_name not in self.terminal_manager.get_all_sessions():
            self.terminal_manager.create_session(session_name, default_dir)

    async def _start_expo_server(self, project_dir: str) -> Dict[str, Any]:
        """Start Expo development server with tunnel mode."""
        return await start_expo_dev_server(
            terminal_manager=self.terminal_manager,
            project_dir=project_dir,
            logger=logger,
            session_name="mobile",
            fallback_to_lan=True,
        )

    async def execute_mcp_wrapper(self):
        """MCP wrapper for the tool."""
        return await self._mcp_wrapper(tool_input={})
