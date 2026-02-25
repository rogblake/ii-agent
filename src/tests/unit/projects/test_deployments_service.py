from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ii_agent.projects.deployments.service import DeploymentsService


@pytest.mark.asyncio
async def test_create_deployment_auto_increments_version(settings_factory, monkeypatch):
    project_repo = AsyncMock()
    deployments_repo = AsyncMock()
    deployments_repo.get_max_version.return_value = 4

    async def _create(db, deployment):
        return deployment

    deployments_repo.create.side_effect = _create
    monkeypatch.setattr(
        "ii_agent.projects.deployments.service.ProjectDeployment",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )

    service = DeploymentsService(
        project_repo=project_repo,
        deployments_repo=deployments_repo,
        config=settings_factory(),
    )

    deployment = await service.create_deployment(
        db=None,
        project_id="project-1",
        user_id="user-1",
        provider="cloud_run",
    )

    assert deployment.version == 5
    assert deployment.deployment_status == "pending"
    assert deployment.started_at is not None


@pytest.mark.asyncio
async def test_update_deployment_status_sets_transition_timestamps(settings_factory):
    project_repo = AsyncMock()
    deployments_repo = AsyncMock()

    deployed = SimpleNamespace(
        id="dep-1",
        deployment_status="pending",
        deployment_url=None,
        error_message=None,
        error_phase=None,
        error_details=None,
        deployed_at=None,
        finished_at=None,
    )
    failed = SimpleNamespace(
        id="dep-2",
        deployment_status="pending",
        deployment_url=None,
        error_message=None,
        error_phase=None,
        error_details=None,
        deployed_at=None,
        finished_at=None,
    )

    deployments_repo.get_by_id.side_effect = [deployed, failed]

    async def _update(db, deployment):
        return deployment

    deployments_repo.update.side_effect = _update

    service = DeploymentsService(
        project_repo=project_repo,
        deployments_repo=deployments_repo,
        config=settings_factory(),
    )

    deployed_result = await service.update_deployment_status(
        db=None,
        deployment_id="dep-1",
        status="deployed",
        deployment_url="https://app.example.com",
    )

    failed_result = await service.update_deployment_status(
        db=None,
        deployment_id="dep-2",
        status="failed",
        error_message="boom",
        error_phase="build",
        error_details={"code": "BUILD_ERR"},
    )

    assert deployed_result.deployed_at is not None
    assert deployed_result.finished_at is not None
    assert deployed_result.deployment_url == "https://app.example.com"

    assert failed_result.deployed_at is None
    assert failed_result.finished_at is not None
    assert failed_result.error_message == "boom"
    assert failed_result.error_phase == "build"
    assert failed_result.error_details == {"code": "BUILD_ERR"}


@pytest.mark.asyncio
async def test_update_deployment_metadata_merges_existing_values(settings_factory):
    project_repo = AsyncMock()
    deployments_repo = AsyncMock()

    deployment = SimpleNamespace(
        id="dep-1",
        deploy_metadata={"source": "snapshot"},
        upload_duration_ms=None,
        build_duration_ms=None,
    )

    deployments_repo.get_by_id.return_value = deployment

    async def _update(db, item):
        return item

    deployments_repo.update.side_effect = _update

    service = DeploymentsService(
        project_repo=project_repo,
        deployments_repo=deployments_repo,
        config=settings_factory(),
    )

    result = await service.update_deployment_metadata(
        db=None,
        deployment_id="dep-1",
        metadata={"region": "us-central1"},
        upload_duration_ms=123,
        build_duration_ms=456,
    )

    assert result.deploy_metadata == {
        "source": "snapshot",
        "region": "us-central1",
    }
    assert result.upload_duration_ms == 123
    assert result.build_duration_ms == 456
