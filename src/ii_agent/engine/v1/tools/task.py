from typing import TYPE_CHECKING, Any, Optional, cast
from ii_agent.engine.v1.agents.agent import IIAgent
from ii_agent.engine.v1.run.agent import RunOutput
from ii_agent.engine.v1.tools.base import BaseAgentTool, ToolResult
from ii_agent.engine.v1.tools.function import FunctionCall
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.engine.v1.run.base import RunContext

# Name
NAME = "sub_agent_task"
DISPLAY_NAME = "Task Agent"

# Tool description
DESCRIPTION = """Launch a new agent that has access to the following tools: TodoRead, TodoWrite, WebVisit, WebSearch, File System Related Tools (Read, Write, Edit, ...) and Bash Related Tools (BashInit, Bash, ...). When you are searching for a keyword or file and are not confident that you will find the right match in the first few tries, use the Task Agent to perform the search for you.

When to use the Task Agent:
- If you are searching for a keyword like "config" or "logger", or for questions like "which file does X?", the Task Agent is strongly recommended

When NOT to use the Task Agent:
- If you want to read a specific file path, use the Read or Glob tool instead of the Task Agent, to find the match more quickly
- If you are searching for a specific class definition like "class Foo", use the Glob tool instead, to find the match more quickly
- If you are searching for code within a specific file or set of 2-3 files, use the Read tool instead of the Task Agent, to find the match more quickly
- Writing code and running bash commands (use other tools for that)
- Other tasks that are not related to searching for a keyword or file

Usage notes:
1. Launch multiple agents concurrently whenever possible, to maximize performance; to do that, use a single message with multiple tool uses
2. When the agent is done, it will return a single message back to you. The result returned by the agent is not visible to the user. To show the user the result, you should send a text message back to the user with a concise summary of the result.
3. Each agent invocation is stateless. You will not be able to send additional messages to the agent, nor will the agent be able to communicate with you outside of its final report. Therefore, your prompt should contain a highly detailed task description for the agent to perform autonomously and you should specify exactly what information the agent should return back to you in its final and only message to you.
4. The agent's outputs should generally be trusted
5. Clearly tell the agent whether you expect it to write code or just to do research (search, file reads, web fetches, etc.), since it is not aware of the user's intent"""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {
            "type": "string",
            "description": "A short (3-5 word) description of the task",
        },
        "prompt": {
            "type": "string",
            "description": "The task for the agent to perform",
        },
    },
    "required": ["description", "prompt"],
}

# System prompt
SYSTEM_PROMPT = """Core Identity
-------------
You are an agent for II Agent, designed to help users with coding tasks, file manipulation, and software development.
- **Workspace Folder**: /workspace
- **Operating System**: ubuntu 24.04 LTS
- Only use ONE sub_agent_task TOOL AT A TIME. DO NOT PARALLEL USE IT. (THIS IS MANDATORY)

Primary Directive
-----------------
Do what has been asked; nothing more, nothing less. When you complete the task, simply respond with a detailed writeup.

File Management Guidelines
--------------------------
- NEVER create files unless they're absolutely necessary for achieving your goal
- ALWAYS prefer editing an existing file to creating a new one
- NEVER proactively create documentation files (*.md) or README files
- Only create documentation files if explicitly requested by the User
- You must use your Read tool at least once before editing any file
- Always use absolute file paths, never relative paths
- When editing files, preserve exact indentation (tabs/spaces)
- Only use emojis if the user explicitly requests it

Communication Guidelines
------------------------
- In final responses, always share relevant file names and code snippets
- All file paths in responses MUST be absolute paths
- Avoid using emojis in communication unless explicitly requested
- Provide detailed writeups when tasks are completed

Bash Command Guidelines
-----------------------
- Always quote file paths with spaces
- Avoid using search commands like find and grep (use Grep/Glob tools instead)
- Avoid read tools like cat, head, tail, ls (use Read/LS tools instead)
- Use ripgrep (rg) instead of grep when needed
- Maintain working directory using absolute paths
- Use semicolon or && to chain commands

Todo List Usage
---------------
Use TodoWrite tool proactively when:
- Complex multi-step tasks (3+ steps)
- Non-trivial and complex tasks
- User explicitly requests todo list
- User provides multiple tasks
- After receiving new instructions

Don't use TodoWrite when:
- Single, straightforward task
- Trivial task with no organizational benefit
- Task completable in less than 3 trivial steps
- Purely conversational or informational tasks

Task Management Rules
--------------------
- Only have ONE task in_progress at a time
- Mark tasks complete IMMEDIATELY after finishing
- Update task status in real-time
- Only mark as completed when FULLY accomplished
- Never mark as completed if tests fail or errors occur

Web Operations
--------------
- Use WebSearch for current events and recent data
- Use WebVisit for analyzing specific URLs

Error Handling
--------------
- If required parameters are missing, ask user to supply them
- Don't make up values for optional parameters
- Use exact values when user provides them (especially in quotes)
- If edit fails due to non-unique string, provide more context

Environment Context
-------------------
The agent operates with awareness of:
- Current working directory
- Platform and OS information
- Today's date
- Available tools and their capabilities

Final Response Requirements
---------------------------
- Provide detailed writeup of completed work
- Include relevant file names and code snippets
- Use absolute paths for all file references
- Avoid emojis unless requested
- Clearly communicate what was accomplished"""


class TaskAgentTool(BaseAgentTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True

    def __init__(
        self,
        agent: IIAgent,
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ):
        self.agent = agent
        self.session_id = session_id
        self.run_id = run_id
        # Parent run_id will be captured in on_tool_start for cancellation purposes
        self._parent_run_id: Optional[str] = None

    async def on_tool_start(
        self,
        agent: "IIAgent",
        fc: "FunctionCall",
        run_context: Optional["RunContext"] = None,
    ) -> None:
        """
        Called before tool execution. Override to add pre-execution logic.

        Args:
            agent: The IIAgent instance executing the tool
            fc: The FunctionCall instance with arguments
            run_context: The run context containing session_state with current_run_id
        """
        if agent.sandbox:
            self.agent.sandbox = agent.sandbox

        # Capture parent's run_id from run_context for cancellation propagation
        # Use run_context.run_id directly (preferred) or fall back to session_state
        if run_context:
            self._parent_run_id = run_context.run_id or (
                run_context.session_state.get("current_run_id")
                if run_context.session_state else None
            )

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        # Use parent's run_id for cancellation checking
        # This ensures when parent is cancelled, sub-agent stops too
        effective_run_id = self._parent_run_id or self.run_id
        agent_output = await self.agent.arun(
            input=tool_input["prompt"],
            stream=False,
            run_id=effective_run_id,  # Use parent's run_id for cancellation
            session_id=self.session_id,
            is_sub_agent=True,
        )
        agent_output = cast(RunOutput, agent_output)
        # Mark as sub-agent response for proper event handling
        agent_output.delegated_from = NAME
        agent_output.parent_run_id = effective_run_id

        return ToolResult(llm_content=agent_output.content)
