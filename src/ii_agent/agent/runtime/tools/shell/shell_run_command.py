from ii_agent.agent.runtime.tools.mcp.base import MCPTool

DEFAULT_TIMEOUT = 60
MAX_TIMEOUT = 180
NAME = "Bash"
DISPLAY_NAME = "Run bash command"
DESCRIPTION = f"""Executes a bash command in a persistent shell session

Usage notes:
- It is very helpful if you write a clear, concise description of what this command does in 5-10 words
- To run multiple commands, join them with ';' or '&&'. Do not use newlines
- For long-running tasks (e.g., deployments), set `wait_for_output` to False and monitor progress with the `BashView` tool
- You can specify an optional timeout in seconds (up to {MAX_TIMEOUT} seconds). If not specified, commands will timeout after {DEFAULT_TIMEOUT} seconds
"""
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "session_name": {
            "type": "string",
            "description": "The name of the session to execute the command in.",
        },
        "command": {"type": "string", "description": "The command to execute."},
        "description": {
            "type": "string",
            "description": "Clear, concise description of what this command does in 5-10 words. Examples:\nInput: ls\nOutput: Lists files in current directory\n\nInput: git status\nOutput: Shows working tree status\n\nInput: npm install\nOutput: Installs package dependencies\n\nInput: mkdir foo\nOutput: Creates directory 'foo'",
        },
        "timeout": {
            "type": "integer",
            "description": "The timeout for the command in seconds. Maximum is {MAX_TIMEOUT} seconds.",
            "default": DEFAULT_TIMEOUT,
        },
        "wait_for_output": {
            "type": "boolean",
            "description": "If True, wait for the command to finish and return its output (up to the timeout). If False, run in background.",
            "default": True,
        },
    },
    "required": ["session_name", "command", "description"],
}


class ShellRunCommand(MCPTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False
