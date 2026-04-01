"""Coverage tests for project design dependency wiring."""

from __future__ import annotations

from types import SimpleNamespace

from ii_agent.projects.design.dependencies import (
    get_project_design_repository,
    _get_project_design_service,
)
from ii_agent.projects.design.repository import ProjectDesignRepository


def test_get_project_design_repository_returns_repository():
    session_repo = object()
    repo = get_project_design_repository(session_repo)
    assert isinstance(repo, ProjectDesignRepository)


def test_get_project_design_service_from_container():
    """Verify _get_project_design_service pulls from container."""

    sentinel = object()

    class FakeContainer(SimpleNamespace):
        project_design_service = sentinel

    result = _get_project_design_service(FakeContainer())
    assert result is sentinel
