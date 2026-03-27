import json
import logging
from typing import TYPE_CHECKING, Any

from ii_agent.agent.runtime.tools.base import TextContent, ToolResult
from ii_agent.agent.runtime.tools.sandbox.base import BaseSandboxTool

if TYPE_CHECKING:
    from ii_agent.agent.runtime.agents.agent import IIAgent
    from ii_agent.agent.runtime.tools.function import FunctionCall

logger = logging.getLogger(__name__)

NAME = "get_server_status"
DISPLAY_NAME = "Get server status"
DESCRIPTION = "Fetch the latest server log output and a screenshot of the current server view."
INPUT_SCHEMA = {"type": "object", "properties": {}, "required": []}

DEFAULT_TIMEOUT = 120


class GetServerStatusTool(BaseSandboxTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        await super().on_tool_start(agent, fc)

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        try:
            output = await self.sandbox.run_command(
                "ii-app web status --workspace /workspace --json",
                timeout=DEFAULT_TIMEOUT,
            )
            result = json.loads(output)
            return ToolResult(
                llm_content=[TextContent(type="text", text=output)],
                user_display_content=result,
            )
        except Exception as e:
            logger.exception("Failed to get server status")
            return ToolResult(
                llm_content=f"Failed to get server status: {e}",
                user_display_content=f"Failed to get server status: {e}",
                is_error=True,
            )
