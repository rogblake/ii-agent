import io
import sys
import tarfile
import types
from unittest.mock import AsyncMock

import pytest

import ii_agent.projects.cloud_run.service as cloud_run_service_module
from ii_agent.projects.cloud_run.schemas import CloudRunConfig, DeploymentStatus, TemplateType
from ii_agent.projects.cloud_run.service import CloudRunPublisher


def _config() -> CloudRunConfig:
    return CloudRunConfig(
        project_id="project-1",
        region="us-central1",
        source_bucket="sources-bucket",
        artifact_registry="us-central1-docker.pkg.dev/project-1/apps",
    )


def _install_fake_policy_pb2(monkeypatch):
    policy_pb2 = types.ModuleType("policy_pb2")

    class Binding:
        def __init__(self, role, members):
            self.role = role
            self.members = members

    class Policy:
        def __init__(self, bindings):
            self.bindings = bindings

    policy_pb2.Binding = Binding
    policy_pb2.Policy = Policy

    google = types.ModuleType("google")
    iam = types.ModuleType("google.iam")
    v1 = types.ModuleType("google.iam.v1")

    google.iam = iam
    iam.v1 = v1
    v1.policy_pb2 = policy_pb2

    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.iam", iam)
    monkeypatch.setitem(sys.modules, "google.iam.v1", v1)
    monkeypatch.setitem(sys.modules, "google.iam.v1.policy_pb2", policy_pb2)


@pytest.mark.asyncio
async def test_sanitize_service_name_handles_invalid_values():
    publisher = CloudRunPublisher(_config())

    assert publisher._sanitize_service_name("123 My__App!!!") == "app-123-my-app"
    assert publisher._sanitize_service_name("----") == "app"

    long_name = "A" * 100
    sanitized = publisher._sanitize_service_name(long_name)
    assert len(sanitized) <= 63
    assert sanitized.startswith("a")


@pytest.mark.asyncio
async def test_create_tarball_excludes_expected_patterns(tmp_path):
    source = tmp_path / "project"
    source.mkdir()

    (source / "app.py").write_text("print('ok')\n")
    (source / "node_modules").mkdir()
    (source / "node_modules" / "lib.js").write_text("ignored\n")
    (source / ".git").mkdir()
    (source / ".git" / "config").write_text("ignored\n")
    (source / "module.pyc").write_text("ignored\n")
    (source / "build").mkdir()
    (source / "build" / "artifact.txt").write_text("ignored\n")

    publisher = CloudRunPublisher(_config())
    tar_bytes = await publisher._create_tarball(source)

    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as archive:
        names = archive.getnames()

    assert "app.py" in names
    assert "node_modules/lib.js" not in names
    assert ".git/config" not in names
    assert "module.pyc" not in names
    assert "build/artifact.txt" not in names


@pytest.mark.asyncio
async def test_publish_maps_build_exceptions_to_failure_result(monkeypatch):
    status_updates = []

    def _on_status(status, message):
        status_updates.append((status, message))

    publisher = CloudRunPublisher(_config(), on_status_update=_on_status)

    monkeypatch.setattr(
        cloud_run_service_module,
        "detect_template_type",
        AsyncMock(return_value=TemplateType.UNKNOWN),
    )
    monkeypatch.setattr(
        cloud_run_service_module,
        "prepare_source_with_dockerfile",
        AsyncMock(return_value=b"prepared"),
    )
    monkeypatch.setattr(publisher, "_upload_source", AsyncMock(return_value="source.tar.gz"))
    monkeypatch.setattr(
        publisher,
        "_build_image",
        AsyncMock(side_effect=RuntimeError("build failed")),
    )

    result = await publisher.publish(
        source_bytes=b"source",
        service_name="My Service",
    )

    assert result.success is False
    assert "build failed" in (result.error or "")
    assert result.service_name == "my-service"
    assert status_updates[-1][0] == DeploymentStatus.FAILED


@pytest.mark.asyncio
async def test_publish_maps_deploy_exceptions_to_failure_result(monkeypatch):
    status_updates = []

    def _on_status(status, message):
        status_updates.append((status, message))

    publisher = CloudRunPublisher(_config(), on_status_update=_on_status)

    monkeypatch.setattr(
        cloud_run_service_module,
        "detect_template_type",
        AsyncMock(return_value=TemplateType.UNKNOWN),
    )
    monkeypatch.setattr(
        cloud_run_service_module,
        "prepare_source_with_dockerfile",
        AsyncMock(return_value=b"prepared"),
    )
    monkeypatch.setattr(publisher, "_upload_source", AsyncMock(return_value="source.tar.gz"))
    monkeypatch.setattr(
        publisher,
        "_build_image",
        AsyncMock(
            return_value={
                "image_url": "image:latest",
                "build_id": "b1",
                "image_digest": "",
                "build_duration_ms": 120,
            }
        ),
    )
    monkeypatch.setattr(
        publisher,
        "_deploy_service",
        AsyncMock(side_effect=RuntimeError("deploy failed")),
    )

    result = await publisher.publish(
        source_bytes=b"source",
        service_name="Another Service",
    )

    assert result.success is False
    assert "deploy failed" in (result.error or "")
    assert result.service_name == "another-service"
    assert status_updates[-1][0] == DeploymentStatus.FAILED


@pytest.mark.asyncio
async def test_allow_unauthenticated_access_calls_set_iam_policy(monkeypatch):
    _install_fake_policy_pb2(monkeypatch)

    publisher = CloudRunPublisher(_config())
    publisher._run_client = AsyncMock()

    service_path = "projects/project-1/locations/us-central1/services/svc"
    await publisher._allow_unauthenticated_access(service_path)

    publisher._run_client.set_iam_policy.assert_awaited_once()
    request = publisher._run_client.set_iam_policy.await_args.kwargs["request"]
    assert request["resource"] == service_path

    policy = request["policy"]
    assert policy.bindings[0].role == "roles/run.invoker"
    assert policy.bindings[0].members == ["allUsers"]
