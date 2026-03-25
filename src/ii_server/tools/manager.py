from ii_server.browser.browser import Browser
from ii_server.core.workspace import WorkspaceManager
from ii_server.interfaces.sandbox import SandboxInterface
from ii_server.tools.dev import (
    FullStackInitTool,
    GetServerStatusTool,
    StripeWebhookRegisterTool,
)
from ii_server.tools.dev.mobile_app_init import MobileAppInitToolInternal
from ii_server.tools.dev.restart_mobile_server import RestartMobileServerToolInternal
from ii_server.tools.dev.restart_server import RestartServerTool
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


def get_common_tools(sandbox: SandboxInterface):
    return []


def get_sandbox_tools(workspace_path: str):
    terminal_manager = TmuxSessionManager()
    workspace_manager = WorkspaceManager(workspace_path)
    browser = Browser()

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
        FullStackInitTool(terminal_manager, workspace_manager),
        MobileAppInitToolInternal(terminal_manager, workspace_manager),
        RestartMobileServerToolInternal(terminal_manager, workspace_manager),
        RestartServerTool(terminal_manager, workspace_manager),
        GetServerStatusTool(terminal_manager, browser),
        StripeWebhookRegisterTool(workspace_manager),
    ]
