from ii_agent.projects.deployment_orchestration_service import DeploymentOrchestrationService


def test_project_path_resolution_and_normalization(settings_factory):
    service = DeploymentOrchestrationService(config=settings_factory())

    session_info = type("SessionInfo", (), {"workspace_dir": "/workspace/s1"})

    assert service.resolve_project_path("./frontend", session_info) == "/workspace/s1/frontend"
    assert service.resolve_project_path(None, session_info) == "/workspace/s1"


def test_project_name_sanitization_for_cloud_run(settings_factory):
    service = DeploymentOrchestrationService(config=settings_factory())

    name = service.resolve_project_name("123 My App!", "/tmp/project", cloud_run=True)

    assert name.startswith("app-")
    assert "my-app" in name
    assert len(name) <= 50


def test_generate_service_name_is_deterministic(settings_factory):
    service = DeploymentOrchestrationService(config=settings_factory())

    first = service.generate_service_name("demo", "session-1")
    second = service.generate_service_name("demo", "session-1")

    assert first == second
    assert len(first[1]) == 8


class _DeploymentsService:
    def __init__(self):
        self.calls = []

    async def update_deployment_status(self, db, deployment_id, status, **kwargs):
        self.calls.append((deployment_id, status, kwargs))


def test_update_deployment_status_noop_without_deployment_id(settings_factory):
    service = DeploymentOrchestrationService(config=settings_factory())

    deployments = _DeploymentsService()

    # Should return early without throwing
    import asyncio

    asyncio.run(
        service.update_deployment_status(
            None,
            "failed",
            deployments_service=deployments,
            error_message="x",
        )
    )

    assert deployments.calls == []
