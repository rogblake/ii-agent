from pathlib import Path

from ii_agent.utils.workspace_manager import WorkspaceManager


def test_workspace_and_container_path_translation(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    manager = WorkspaceManager(root=root, container_workspace=Path("/workspace"))

    local = manager.workspace_path("src/app.py")
    container = manager.container_path(local)

    assert local == root / "src/app.py"
    assert container == Path("/workspace/src/app.py")


def test_workspace_path_maps_container_path_back_to_local(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    manager = WorkspaceManager(root=root, container_workspace=Path("/workspace"))

    local = manager.workspace_path("/workspace/sub/file.txt")

    assert local == root / "sub/file.txt"


def test_relative_path_returns_absolute_when_outside_root(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    manager = WorkspaceManager(root=root)

    outside = tmp_path / "other" / "a.txt"
    outside.parent.mkdir()

    assert manager.relative_path(outside) == outside
