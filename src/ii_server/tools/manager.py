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
from ii_server.tools.shell import (
    ShellInit,
    ShellList,
    ShellRunCommand,
    ShellStopCommand,
    ShellView,
    ShellWriteToProcessTool,
    TmuxSessionManager,
)


def get_common_tools():
    return []


def get_sandbox_tools(workspace_path: str):
    terminal_manager = TmuxSessionManager()
    workspace_manager = WorkspaceManager(workspace_path)

    return [
        ShellInit(terminal_manager, workspace_manager),
        ShellRunCommand(terminal_manager, workspace_manager),
        ShellView(terminal_manager),
        ShellStopCommand(terminal_manager),
        ShellList(terminal_manager),
        ShellWriteToProcessTool(terminal_manager),
        FileReadTool(workspace_manager),
        FileWriteTool(workspace_manager),
        FileEditTool(workspace_manager),
        ApplyPatchTool(workspace_manager),
        StrReplaceEditorTool(workspace_manager),
        ASTGrepTool(workspace_manager),
        GrepTool(workspace_manager),
    ]
