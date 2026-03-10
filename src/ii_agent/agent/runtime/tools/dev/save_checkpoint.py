from ii_agent.agent.runtime.tools.mcp.base import MCPTool

NAME = "save_checkpoint"
DISPLAY_NAME = "Save checkpoint"
DESCRIPTION = (
    "Save a checkpoint of the work the agents have done. This must be called after the user's task is done, or after a major change have been implemented."
    "Always call this tool when you have done testing and ensure the required functionalities are implemented"
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "project_directory": {
            "type": "string",
            "description": "Absolute or workspace-relative path to the project root.",
        },
        "commit_message": {
            "type": "string",
            "description": "git commit message (default: 'Checkpoint').",
        },
    },
    "required": ["project_directory", "commit_message"],
}


class SaveCheckpointTool(MCPTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False
