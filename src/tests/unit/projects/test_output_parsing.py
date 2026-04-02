from ii_agent.projects.deployment_orchestration_service import DeploymentOrchestrationService


def test_success_marker_append_detect_cleanup(settings_factory):
    service = DeploymentOrchestrationService(config=settings_factory())

    cmd = service.append_success_marker("npm run deploy")

    assert "__II_PUBLISH_SUCCESS__" in cmd
    assert service.command_succeeded("log\n__II_PUBLISH_SUCCESS__") is True
    assert service.cleanup_output("ok\n__II_PUBLISH_SUCCESS__") == "ok"


def test_redact_secrets_patterns(settings_factory):
    service = DeploymentOrchestrationService(config=settings_factory())

    output = "vercel --token abc123 VERCEL_TOKEN=xyz"
    redacted = service.redact_secrets(output)

    assert "abc123" not in redacted
    assert "xyz" not in redacted
    assert "[REDACTED]" in redacted


def test_extract_deployment_url_precedence(settings_factory):
    service = DeploymentOrchestrationService(config=settings_factory())

    output = "Build done. Production: https://my-app.vercel.app"
    url = service.extract_deployment_url(output, "fallback")

    assert url == "https://my-app.vercel.app"
    assert service.extract_deployment_url("", "fallback") == "https://fallback.vercel.app"
