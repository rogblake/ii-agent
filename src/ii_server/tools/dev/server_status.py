"""Tool for getting development server status."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from playwright.async_api import TimeoutError

from ii_server.browser.browser import Browser
from ii_server.core.models import DeploymentConfig
from ii_server.core.tool_server_config import get_tool_server_config
from ii_server.logger import get_logger
from ii_server.tools.base import BaseTool, ImageContent, TextContent, ToolResult
from ii_server.tools.shell.terminal_manager import (
    BaseShellManager,
    ShellError,
    ShellSessionNotFoundError,
)

logger = get_logger(__name__)

NAME = "get_server_status"
DISPLAY_NAME = "Get server status"
DESCRIPTION = "Fetch the latest server log output and a screenshot of the current server view."

INPUT_SCHEMA = {"type": "object", "properties": {}, "required": []}

class GetServerStatusTool(BaseTool):
    """Tool to get the current status of development servers."""

    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True

    def __init__(self, terminal_manager: BaseShellManager, browser: Browser) -> None:
        super().__init__()
        self.terminal_manager = terminal_manager
        self.browser = browser

    def _get_deployment_config(self) -> Optional[DeploymentConfig]:
        """Get the deployment config."""
        return get_tool_server_config().get_deployment_config()

    def _default_session(self, config: Optional[DeploymentConfig]) -> Optional[str]:
        """Get the default session name from config."""
        if not config or not config.servers:
            return None
        return config.servers[0].session

    def _default_url(self, config: Optional[DeploymentConfig]) -> Optional[str]:
        """Get the default URL from config."""
        if not config:
            return None
        if config.preview_url:
            return config.preview_url
        if config.servers:
            return config.servers[0].deployment_url
        return None

    def _is_previewable_url(self, url: str) -> bool:
        """Check if a URL can be previewed in a browser."""
        if not url:
            return False
        if url.startswith("http://") or url.startswith("https://"):
            return True
        if url.startswith("Expose port"):
            return False
        return False

    async def _screenshot(self, url: str) -> Optional[ImageContent]:
        """Capture a screenshot of the given URL."""
        page = await self.browser.get_current_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(1.5)
        except TimeoutError:
            logger.warning("Timed out capturing screenshot for %s", url)
            return None
        except Exception as exc:
            logger.warning("Failed to capture screenshot for %s: %s", url, exc)
            return None

        state = await self.browser.update_state()
        state = await self.browser.handle_pdf_url_navigation()
        return ImageContent(type="image", data=state.screenshot, mime_type="image/png")

    async def execute(
        self,
        tool_input: Dict[str, Any],
    ) -> ToolResult:
        """Execute the status check."""
        config = self._get_deployment_config()
        session = self._default_session(config)

        if not session:
            return ToolResult(
                llm_content="No session provided and no deployment config found to infer a session.",
                user_display_content="Session name required.",
                is_error=True,
            )

        try:
            output = self.terminal_manager.get_session_output(session)
        except (ShellSessionNotFoundError, ShellError) as exc:
            return ToolResult(
                llm_content=f"Failed to fetch logs for session '{session}': {exc}",
                user_display_content=f"Failed to fetch logs for session '{session}'.",
                is_error=True,
            )

        url = self._default_url(config)
        image_content: Optional[ImageContent] = None
        if url and self._is_previewable_url(url):
            image_content = await self._screenshot(url)
        elif url:
            logger.info("Skipping screenshot for non-previewable url: %s", url)

        text = TextContent(
            type="text",
            text=f"Session `{session}` output:\n{output.clean_output}",
        )

        llm_payload = [text]
        if image_content:
            llm_payload = [image_content, text]

        user_display: Dict[str, Any] = {
            "session": session,
            "output": output.clean_output,
        }
        if image_content:
            user_display["screenshot"] = image_content.model_dump()
            user_display["url"] = url

        return ToolResult(
            llm_content=llm_payload,
            user_display_content=user_display,
            is_error=False,
        )

    async def execute_mcp_wrapper(
        self, session: str | None = None, url: str | None = None
    ):
        """MCP wrapper for execute."""
        payload: Dict[str, Any] = {}
        if session:
            payload["session"] = session
        if url:
            payload["url"] = url
        return await self._mcp_wrapper(tool_input=payload)
