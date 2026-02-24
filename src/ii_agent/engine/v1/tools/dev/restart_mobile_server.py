"""Restart the Expo mobile app development server."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ii_agent.engine.v1.tools.base import TextContent, ToolResult
from ii_agent.engine.v1.tools.mcp.base import MCPTool

if TYPE_CHECKING:
    from ii_agent.engine.v1.agents.agent import IIAgent
    from ii_agent.engine.v1.tools.function import FunctionCall

logger = logging.getLogger(__name__)

NAME = "restart_mobile_server"
DISPLAY_NAME = "Restart Mobile App Server"
DESCRIPTION = """Restarts the Expo mobile app development server.

Returns refreshed tunnel/QR details and exposes web preview URL when possible.
"""
INPUT_SCHEMA = {"type": "object", "properties": {}, "required": []}


class RestartMobileServerTool(MCPTool):
    """Tool for restarting Expo mobile app server."""

    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        await super().on_tool_start(agent, fc)

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        result = await super().execute(tool_input)

        if not result.is_error and isinstance(result.user_display_content, dict):
            web_port = result.user_display_content.get("web_port", 8081)
            try:
                if hasattr(self, "sandbox") and self.sandbox:
                    web_preview_url = await self.sandbox.expose_port(web_port)
                    result.user_display_content["web_preview_url"] = web_preview_url

                    if isinstance(result.llm_content, list) and result.llm_content:
                        first_content = result.llm_content[0]
                        if hasattr(first_content, "text"):
                            updated_text = (
                                first_content.text
                                + f"\n- **Web Preview URL:** `{web_preview_url}`"
                            )
                            result.llm_content[0] = TextContent(
                                type="text",
                                text=updated_text,
                            )
            except Exception as port_error:  # noqa: BLE001
                logger.warning("Failed to expose port %s: %s", web_port, port_error)

        return result
