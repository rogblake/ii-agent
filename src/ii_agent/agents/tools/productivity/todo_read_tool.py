from typing import Any, Optional, TYPE_CHECKING
from ii_agent.agents.tools.base import BaseAgentTool, ToolResult
from ii_agent.core.container import get_app_container
from ii_agent.core.db import get_db_session_local

if TYPE_CHECKING:
    from ii_agent.agents.agent import IIAgent
    from ii_agent.agents.tools.function import FunctionCall

NAME = "TodoRead"
DISPLAY_NAME = "Read todo list"
DESCRIPTION = """Use this tool to read the current to-do list for the session. This tool should be used proactively and frequently to ensure that you are aware of
the status of the current task list. You should make use of this tool as often as possible, especially in the following situations:
- At the beginning of conversations to see what's pending
- Before starting new tasks to prioritize work
- When the user asks about previous tasks or plans
- Whenever you're uncertain about what to do next
- After completing tasks to update your understanding of remaining work
- After every few messages to ensure you're on track

Usage:
- This tool takes in no parameters. So leave the input blank or empty. DO NOT include a dummy object, placeholder string or a key like \"input\" or \"empty\". LEAVE IT BLANK.
- Returns a list of todo items with their status, priority, and content
- Use this information to track progress and plan next steps
- If no todos exist yet, an empty list will be returned"""
INPUT_SCHEMA = {"type": "object", "properties": {}}
EMPTY_MESSAGE = "No todos found"
SUCCESS_MESSAGE = "Remember to continue to use update and read from the todo list as you make progress. Here is the current list: {todos}"
TODO_METADATA_KEY = "todos"


class TodoReadTool(BaseAgentTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True

    def __init__(self):
        self._session_id: Optional[str] = None

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        await super().on_tool_start(agent, fc)
        self._session_id = agent.session_id

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        if not self._session_id:
            return ToolResult(
                llm_content="No active session found for todo list.",
                is_error=True,
            )

        async with get_db_session_local() as db:
            session = await get_app_container().session_service.get_session_by_id(
                db, self._session_id
            )
            if not session:
                return ToolResult(
                    llm_content="Session not found for todo list.",
                    is_error=True,
                )

            session_metadata = session.session_metadata or {}
            todos = session_metadata.get(TODO_METADATA_KEY, [])

        if not isinstance(todos, list) or not todos:
            return ToolResult(llm_content=EMPTY_MESSAGE, is_error=False)

        return ToolResult(
            llm_content=SUCCESS_MESSAGE.format(todos=todos),
            is_error=False,
        )
