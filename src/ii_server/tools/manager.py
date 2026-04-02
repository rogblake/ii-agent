from ii_server.core.workspace import WorkspaceManager
from ii_server.tools.file_system import (
    ASTGrepTool,
    ApplyPatchTool,
    FileEditTool,
    FileReadTool,
    FileWriteTool,
    GrepTool,
    StrReplaceEditorTool,
)


def get_common_tools():
    return []


def get_sandbox_tools(workspace_path: str):
    workspace_manager = WorkspaceManager(workspace_path)

    return [
        FileReadTool(workspace_manager),
        FileWriteTool(workspace_manager),
        FileEditTool(workspace_manager),
        ApplyPatchTool(workspace_manager),
        StrReplaceEditorTool(workspace_manager),
        ASTGrepTool(workspace_manager),
        GrepTool(workspace_manager),
    ]
