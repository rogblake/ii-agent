from ii_agent.projects.deployment_orchestration_service import DeploymentOrchestrationService

import pytest

pytestmark = pytest.mark.integration


def test_deployment_context_utility_flow(settings_factory):
    service = DeploymentOrchestrationService(config=settings_factory())

    project_path = service.resolve_project_path("./frontend", type("Session", (), {"workspace_dir": "/workspace/s1"}))
    project_name = service.resolve_project_name("My App", project_path, cloud_run=False)
    service_name, suffix = service.generate_service_name(project_name, "session-1", prefix="ii")

    assert project_path == "/workspace/s1/frontend"
    assert project_name == "my-app"
    assert service_name.startswith("ii-my-app-")
    assert len(suffix) == 8
