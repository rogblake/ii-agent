"""Restart the Expo mobile app development server."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from ii_agent.agent.runtime.tools.base import TextContent, ToolResult
from ii_agent.agent.runtime.tools.sandbox.base import BaseSandboxTool

if TYPE_CHECKING:
    from ii_agent.agent.runtime.agents.agent import IIAgent
    from ii_agent.agent.runtime.tools.function import FunctionCall

logger = logging.getLogger(__name__)

NAME = "restart_mobile_server"
DISPLAY_NAME = "Restart Mobile App Server"
DESCRIPTION = """Restarts the Expo mobile app development server.

Returns refreshed tunnel/QR details and exposes web preview URL when possible.
"""
INPUT_SCHEMA = {"type": "object", "properties": {}, "required": []}

DEFAULT_TIMEOUT = 180


class RestartMobileServerTool(BaseSandboxTool):
    """Tool for restarting Expo mobile app server."""

    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        await super().on_tool_start(agent, fc)

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        try:
            output = await self.sandbox.run_command(
                "ii-app mobile restart --workspace /workspace --json",
                timeout=DEFAULT_TIMEOUT,
            )
            result = json.loads(output)

            # Expose web preview URL if available
            web_port = result.get("web_port", 8081)
            try:
                web_preview_url = await self.sandbox.expose_port(web_port)
                result["web_preview_url"] = web_preview_url
            except Exception as port_error:
                logger.warning("Failed to expose port %s: %s", web_port, port_error)

            return ToolResult(
                llm_content=[TextContent(type="text", text=json.dumps(result))],
                user_display_content=result,
            )
        except Exception as e:
            logger.exception("Failed to restart mobile server")
            return ToolResult(
                llm_content=f"Failed to restart mobile server: {e}",
                user_display_content=f"Failed to restart mobile server: {e}",
                is_error=True,
            )
