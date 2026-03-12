"""Coverage tests for project design dependency wiring."""
from __future__ import annotations

from types import SimpleNamespace

from ii_agent.projects.design.dependencies import (
    get_project_design_repository,
    get_project_design_service,
)
from ii_agent.projects.design.repository import ProjectDesignRepository


def test_get_project_design_repository_returns_repository():
    session_repo = object()
    repo = get_project_design_repository(session_repo)
    assert isinstance(repo, ProjectDesignRepository)


def test_get_project_design_service_builds_service_with_config(monkeypatch):
    created = {}

    class FakeService:
        def __init__(
            self,
            *,
            repo,
            sandbox_service,
            llm_setting_service,
            llm_billing_service,
            llm_execution_service,
            config,
        ) -> None:
            created["repo"] = repo
            created["sandbox_service"] = sandbox_service
            created["llm_setting_service"] = llm_setting_service
            created["llm_billing_service"] = llm_billing_service
            created["llm_execution_service"] = llm_execution_service
            created["config"] = config

    class FakeSettings(SimpleNamespace):
        env = "test"

    monkeypatch.setattr("ii_agent.projects.design.dependencies.ProjectDesignService", FakeService)
    monkeypatch.setattr("ii_agent.projects.design.dependencies.get_settings", lambda: FakeSettings())

    repository = get_project_design_repository(object())
    service = get_project_design_service(
        design_repo=repository,
        sandbox_service=object(),
        llm_setting_service=object(),
        llm_billing_service=object(),
        llm_execution_service=object(),
    )

    assert isinstance(service, FakeService)
    assert created["repo"] is repository
    assert created["config"].env == "test"
    assert isinstance(created["sandbox_service"], object)
