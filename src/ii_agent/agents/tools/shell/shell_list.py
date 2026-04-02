from ii_agent.agents.tools.base import ToolResult
from ii_agent.agents.tools.sandbox.base import BaseSandboxTool

NAME = "BashList"
DISPLAY_NAME = "List bash sessions"
DESCRIPTION = "List all available bash sessions"
INPUT_SCHEMA = {"type": "object", "properties": {}}


class ShellList(BaseSandboxTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True

    async def execute(self, tool_input: dict) -> ToolResult:
        all_current_sessions = await self.sandbox.get_all_shell_sessions()
        result = f"Available sessions: {all_current_sessions}\n"
        result += "For the detailed output of a session, use `BashView`."
        return ToolResult(llm_content=result, is_error=False)
