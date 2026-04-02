import json
import logging
from typing import TYPE_CHECKING, Any

from ii_agent.agents.tools.base import TextContent, ToolResult
from ii_agent.agents.tools.sandbox.base import BaseSandboxTool

if TYPE_CHECKING:
    from ii_agent.agents.agent import IIAgent
    from ii_agent.agents.tools.function import FunctionCall

logger = logging.getLogger(__name__)

NAME = "get_server_status"
DISPLAY_NAME = "Get server status"
DESCRIPTION = "Fetch the latest server log output and a screenshot of the current server view."
INPUT_SCHEMA = {"type": "object", "properties": {}, "required": []}

DEFAULT_TIMEOUT = 120
_WEB_CACHE_NOT_FOUND_MARKER = "web cache not found."
_WEB_CACHE_PATHS = "/workspace/.ii-app/web.json or /workspace/.ii-web-server/cache.json"


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
            if _WEB_CACHE_NOT_FOUND_MARKER in str(e).lower():
                message = (
                    "Server status is unavailable because the web cache is missing. "
                    f"Expected {_WEB_CACHE_PATHS}. The web app may not be initialized "
                    "yet, or a previous init failed and cleaned up the cache."
                )
                result = ToolResult(
                    llm_content=message,
                    user_display_content=message,
                    is_error=False,
                )
                logger.warning(result.llm_content)
                return result
            logger.exception("Failed to get server status")
            return ToolResult(
                llm_content=f"Failed to get server status: {e}",
                user_display_content=f"Failed to get server status: {e}",
                is_error=True,
            )
