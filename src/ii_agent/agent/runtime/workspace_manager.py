from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ii_agent.core.config.settings import Settings


class WorkspaceManager:
    root: Path

    def __init__(self, root: Path, container_workspace: Path | None = None):
        self.root = root.absolute()
        self.container_workspace = container_workspace

    @classmethod
    def from_settings(cls, settings: "Settings") -> "WorkspaceManager":
        container_workspace = (
            Path(settings.workspace_path) if settings.use_container_workspace else None
        )
        return cls(
            root=Path(settings.workspace_root),
            container_workspace=container_workspace,
        )

    def workspace_path(self, path: Path | str) -> Path:
        """Given a path, possibly in a container workspace, return the absolute local path."""
        path = Path(path)
        if not path.is_absolute():
            return self.root / path
        if self.container_workspace and path.is_relative_to(self.container_workspace):
            return self.root / path.relative_to(self.container_workspace)
        return path

    def container_path(self, path: Path | str) -> Path:
        """Given a path, possibly in the local workspace, return the absolute container path.
        If there is no container workspace, return the absolute local path.
        """
        path = Path(path)
        if not path.is_absolute():
            if self.container_workspace:
                return self.container_workspace / path
            return self.root / path
        if self.container_workspace and path.is_relative_to(self.root):
            return self.container_workspace / path.relative_to(self.root)
        return path

    def relative_path(self, path: Path | str) -> Path:
        """Given a path, return the relative path from the workspace root.
        If the path is not under the workspace root, returns the absolute path.
        """
        path = Path(path)
        abs_path = self.workspace_path(path)
        try:
            return abs_path.relative_to(self.root.absolute())
        except ValueError:
            return abs_path
