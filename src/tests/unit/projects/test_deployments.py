"""Unit tests for projects/deployments/service.py.

Covers:
- DeploymentsService.get_project_deployment – project not found, deployment not found, happy path
- DeploymentsService.create_deployment – auto-increment version, default status
- DeploymentsService.update_deployment_status – status transitions, url/error setting
- DeploymentsService.update_deployment_metadata – metadata merge, performance metrics
- DeploymentsService.set_active_deployment – project production_url update
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.projects.deployments.exceptions import DeploymentNotFoundError
from ii_agent.projects.exceptions import ProjectNotFoundError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_deployment(
    *,
    id_=None,
    project_id="proj-1",
    user_id="u-1",
    provider="cloud_run",
    status="pending",
    url=None,
    version=1,
    error_message=None,
    error_phase=None,
    error_details=None,
    deploy_metadata=None,
    upload_duration_ms=None,
    build_duration_ms=None,
    deployed_at=None,
    finished_at=None,
):
    d = SimpleNamespace()
    d.id = id_ or str(uuid.uuid4())
    d.project_id = project_id
    d.deployed_by_user_id = user_id
    d.provider = provider
    d.deployment_status = status
    d.deployment_url = url
    d.version = version
    d.error_message = error_message
    d.error_phase = error_phase
    d.error_details = error_details
    d.deploy_metadata = deploy_metadata
    d.upload_duration_ms = upload_duration_ms
    d.build_duration_ms = build_duration_ms
    d.deployed_at = deployed_at
    d.finished_at = finished_at
    return d


def _make_project(id_="proj-1", user_id="u-1", production_url=None):
    p = SimpleNamespace()
    p.id = id_
    p.user_id = user_id
    p.production_url = production_url
    return p


def _make_service(*, project_repo=None, deployments_repo=None, config=None):
    from ii_agent.projects.deployments.service import DeploymentsService

    if project_repo is None:
        project_repo = MagicMock()
    if deployments_repo is None:
        deployments_repo = MagicMock()
    if config is None:
        config = MagicMock()

    return DeploymentsService(
        project_repo=project_repo,
        deployments_repo=deployments_repo,
        config=config,
    )


# ===========================================================================
# get_project_deployment
# ===========================================================================


class TestGetProjectDeployment:
    async def test_raises_project_not_found_when_project_missing(self):
        project_repo = MagicMock()
        project_repo.get_by_id_and_user = AsyncMock(return_value=None)
        svc = _make_service(project_repo=project_repo)

        with pytest.raises(ProjectNotFoundError):
            await svc.get_project_deployment(AsyncMock(), user_id="u-1", project_id="missing")

    async def test_raises_deployment_not_found_when_no_deployment(self):
        project_repo = MagicMock()
        project_repo.get_by_id_and_user = AsyncMock(return_value=_make_project())

        deployments_repo = MagicMock()
        deployments_repo.get_latest_deployment = AsyncMock(return_value=None)

        svc = _make_service(project_repo=project_repo, deployments_repo=deployments_repo)

        with pytest.raises(DeploymentNotFoundError):
            await svc.get_project_deployment(AsyncMock(), user_id="u-1", project_id="proj-1")

    async def test_returns_deployment_on_success(self):
        project = _make_project()
        deployment = _make_deployment()

        project_repo = MagicMock()
        project_repo.get_by_id_and_user = AsyncMock(return_value=project)

        deployments_repo = MagicMock()
        deployments_repo.get_latest_deployment = AsyncMock(return_value=deployment)

        svc = _make_service(project_repo=project_repo, deployments_repo=deployments_repo)

        result = await svc.get_project_deployment(AsyncMock(), user_id="u-1", project_id="proj-1")
        assert result is deployment

    async def test_queries_with_provider_none(self):
        project = _make_project()
        deployment = _make_deployment()

        project_repo = MagicMock()
        project_repo.get_by_id_and_user = AsyncMock(return_value=project)

        deployments_repo = MagicMock()
        deployments_repo.get_latest_deployment = AsyncMock(return_value=deployment)

        svc = _make_service(project_repo=project_repo, deployments_repo=deployments_repo)

        await svc.get_project_deployment(AsyncMock(), user_id="u-1", project_id="proj-1")

        deployments_repo.get_latest_deployment.assert_called_once()
        call_kwargs = deployments_repo.get_latest_deployment.call_args[1]
        assert call_kwargs.get("provider") is None


# ===========================================================================
# create_deployment
# ===========================================================================


class TestCreateDeployment:
    """Uses monkeypatching to avoid SQLAlchemy mapper resolution issues."""

    async def test_creates_deployment_with_auto_incremented_version(self, monkeypatch):
        created_deployments = []

        deployments_repo = MagicMock()
        deployments_repo.get_max_version = AsyncMock(return_value=3)

        async def fake_create(db, deployment):
            created_deployments.append(deployment)
            return deployment

        deployments_repo.create = fake_create

        monkeypatch.setattr(
            "ii_agent.projects.deployments.service.ProjectDeployment",
            lambda **kwargs: SimpleNamespace(**kwargs),
        )

        svc = _make_service(deployments_repo=deployments_repo)

        result = await svc.create_deployment(
            AsyncMock(),
            project_id="proj-1",
            user_id="u-1",
            provider="cloud_run",
        )

        assert result.version == 4  # 3 + 1

    async def test_new_deployment_has_pending_status(self, monkeypatch):
        deployments_repo = MagicMock()
        deployments_repo.get_max_version = AsyncMock(return_value=0)

        async def fake_create(db, deployment):
            return deployment

        deployments_repo.create = fake_create

        monkeypatch.setattr(
            "ii_agent.projects.deployments.service.ProjectDeployment",
            lambda **kwargs: SimpleNamespace(**kwargs),
        )

        svc = _make_service(deployments_repo=deployments_repo)

        result = await svc.create_deployment(
            AsyncMock(),
            project_id="proj-1",
            user_id="u-1",
            provider="vercel",
        )

        assert result.deployment_status == "pending"

    async def test_first_deployment_has_version_1(self, monkeypatch):
        deployments_repo = MagicMock()
        deployments_repo.get_max_version = AsyncMock(return_value=0)

        async def fake_create(db, deployment):
            return deployment

        deployments_repo.create = fake_create

        monkeypatch.setattr(
            "ii_agent.projects.deployments.service.ProjectDeployment",
            lambda **kwargs: SimpleNamespace(**kwargs),
        )

        svc = _make_service(deployments_repo=deployments_repo)

        result = await svc.create_deployment(
            AsyncMock(),
            project_id="proj-1",
            user_id="u-1",
            provider="cloud_run",
        )

        assert result.version == 1

    async def test_source_path_and_snapshot_id_stored(self, monkeypatch):
        deployments_repo = MagicMock()
        deployments_repo.get_max_version = AsyncMock(return_value=0)

        async def fake_create(db, deployment):
            return deployment

        deployments_repo.create = fake_create

        monkeypatch.setattr(
            "ii_agent.projects.deployments.service.ProjectDeployment",
            lambda **kwargs: SimpleNamespace(**kwargs),
        )

        svc = _make_service(deployments_repo=deployments_repo)

        result = await svc.create_deployment(
            AsyncMock(),
            project_id="proj-1",
            user_id="u-1",
            provider="cloud_run",
            source_path="/workspace/app",
            snapshot_id="abc123",
        )

        assert result.source_path == "/workspace/app"
        assert result.snapshot_id == "abc123"

    async def test_deployment_id_is_uuid(self, monkeypatch):
        deployments_repo = MagicMock()
        deployments_repo.get_max_version = AsyncMock(return_value=0)

        async def fake_create(db, deployment):
            return deployment

        deployments_repo.create = fake_create

        monkeypatch.setattr(
            "ii_agent.projects.deployments.service.ProjectDeployment",
            lambda **kwargs: SimpleNamespace(**kwargs),
        )

        svc = _make_service(deployments_repo=deployments_repo)

        result = await svc.create_deployment(
            AsyncMock(),
            project_id="p",
            user_id="u",
            provider="cloud_run",
        )

        # Should be parseable as UUID
        uuid.UUID(result.id)


# ===========================================================================
# update_deployment_status
# ===========================================================================


class TestUpdateDeploymentStatus:
    async def test_returns_none_when_deployment_not_found(self):
        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=None)

        svc = _make_service(deployments_repo=deployments_repo)

        result = await svc.update_deployment_status(
            AsyncMock(), deployment_id="missing", status="deployed"
        )
        assert result is None

    async def test_updates_status(self):
        deployment = _make_deployment(status="building")
        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=deployment)
        deployments_repo.update = AsyncMock(return_value=deployment)

        svc = _make_service(deployments_repo=deployments_repo)

        await svc.update_deployment_status(AsyncMock(), deployment_id="d-1", status="deployed")
        assert deployment.deployment_status == "deployed"

    async def test_deployed_sets_deployed_at_and_finished_at(self):
        deployment = _make_deployment()
        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=deployment)
        deployments_repo.update = AsyncMock(return_value=deployment)

        svc = _make_service(deployments_repo=deployments_repo)

        before = datetime.now(timezone.utc)
        await svc.update_deployment_status(AsyncMock(), deployment_id="d-1", status="deployed")

        assert deployment.deployed_at is not None
        assert deployment.finished_at is not None
        assert deployment.deployed_at >= before

    async def test_failed_sets_only_finished_at(self):
        deployment = _make_deployment()
        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=deployment)
        deployments_repo.update = AsyncMock(return_value=deployment)

        svc = _make_service(deployments_repo=deployments_repo)

        await svc.update_deployment_status(AsyncMock(), deployment_id="d-1", status="failed")

        assert deployment.finished_at is not None
        assert deployment.deployed_at is None  # Not set for 'failed'

    async def test_other_status_does_not_set_timestamps(self):
        deployment = _make_deployment()
        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=deployment)
        deployments_repo.update = AsyncMock(return_value=deployment)

        svc = _make_service(deployments_repo=deployments_repo)

        await svc.update_deployment_status(AsyncMock(), deployment_id="d-1", status="building")

        assert deployment.deployed_at is None
        assert deployment.finished_at is None

    async def test_url_set_when_provided(self):
        deployment = _make_deployment()
        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=deployment)
        deployments_repo.update = AsyncMock(return_value=deployment)

        svc = _make_service(deployments_repo=deployments_repo)

        await svc.update_deployment_status(
            AsyncMock(),
            deployment_id="d-1",
            status="deployed",
            deployment_url="https://my-app.run.app",
        )

        assert deployment.deployment_url == "https://my-app.run.app"

    async def test_url_not_set_when_not_provided(self):
        deployment = _make_deployment(url="old-url")
        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=deployment)
        deployments_repo.update = AsyncMock(return_value=deployment)

        svc = _make_service(deployments_repo=deployments_repo)

        await svc.update_deployment_status(AsyncMock(), deployment_id="d-1", status="deployed")

        # URL should remain unchanged
        assert deployment.deployment_url == "old-url"

    async def test_error_details_set_when_provided(self):
        deployment = _make_deployment()
        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=deployment)
        deployments_repo.update = AsyncMock(return_value=deployment)

        svc = _make_service(deployments_repo=deployments_repo)

        await svc.update_deployment_status(
            AsyncMock(),
            deployment_id="d-1",
            status="failed",
            error_message="Build failed",
            error_phase="build",
            error_details={"code": "E001"},
        )

        assert deployment.error_message == "Build failed"
        assert deployment.error_phase == "build"
        assert deployment.error_details == {"code": "E001"}


# ===========================================================================
# update_deployment_metadata
# ===========================================================================


class TestUpdateDeploymentMetadata:
    async def test_returns_none_when_deployment_not_found(self):
        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=None)

        svc = _make_service(deployments_repo=deployments_repo)

        result = await svc.update_deployment_metadata(
            AsyncMock(), deployment_id="missing", metadata={"key": "val"}
        )
        assert result is None

    async def test_merges_metadata_with_existing(self):
        deployment = _make_deployment(deploy_metadata={"existing": "data"})
        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=deployment)
        deployments_repo.update = AsyncMock(return_value=deployment)

        svc = _make_service(deployments_repo=deployments_repo)

        await svc.update_deployment_metadata(
            AsyncMock(),
            deployment_id="d-1",
            metadata={"new_key": "new_val"},
        )

        assert deployment.deploy_metadata["existing"] == "data"
        assert deployment.deploy_metadata["new_key"] == "new_val"

    async def test_metadata_created_when_none_before(self):
        deployment = _make_deployment(deploy_metadata=None)
        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=deployment)
        deployments_repo.update = AsyncMock(return_value=deployment)

        svc = _make_service(deployments_repo=deployments_repo)

        await svc.update_deployment_metadata(
            AsyncMock(),
            deployment_id="d-1",
            metadata={"key": "val"},
        )

        assert deployment.deploy_metadata == {"key": "val"}

    async def test_sets_upload_duration_ms(self):
        deployment = _make_deployment()
        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=deployment)
        deployments_repo.update = AsyncMock(return_value=deployment)

        svc = _make_service(deployments_repo=deployments_repo)

        await svc.update_deployment_metadata(
            AsyncMock(),
            deployment_id="d-1",
            upload_duration_ms=1200,
        )

        assert deployment.upload_duration_ms == 1200

    async def test_sets_build_duration_ms(self):
        deployment = _make_deployment()
        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=deployment)
        deployments_repo.update = AsyncMock(return_value=deployment)

        svc = _make_service(deployments_repo=deployments_repo)

        await svc.update_deployment_metadata(
            AsyncMock(),
            deployment_id="d-1",
            build_duration_ms=45000,
        )

        assert deployment.build_duration_ms == 45000

    async def test_noop_when_all_none(self):
        """If all args are None, nothing changes."""
        deployment = _make_deployment(deploy_metadata={"k": "v"})
        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=deployment)
        deployments_repo.update = AsyncMock(return_value=deployment)

        svc = _make_service(deployments_repo=deployments_repo)

        await svc.update_deployment_metadata(AsyncMock(), deployment_id="d-1")

        assert deployment.deploy_metadata == {"k": "v"}
        assert deployment.upload_duration_ms is None
        assert deployment.build_duration_ms is None


# ===========================================================================
# set_active_deployment
# ===========================================================================


class TestSetActiveDeployment:
    async def test_returns_none_when_deployment_not_found(self):
        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=None)

        svc = _make_service(deployments_repo=deployments_repo)

        result = await svc.set_active_deployment(
            AsyncMock(), project_id="p-1", deployment_id="missing"
        )
        assert result is None

    async def test_updates_project_production_url_when_deployment_has_url(self):
        project = _make_project()
        deployment = _make_deployment(url="https://my-app.run.app")

        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=deployment)

        project_repo = MagicMock()
        project_repo.get_by_id = AsyncMock(return_value=project)
        project_repo.update = AsyncMock(return_value=project)

        svc = _make_service(project_repo=project_repo, deployments_repo=deployments_repo)

        result = await svc.set_active_deployment(
            AsyncMock(), project_id="proj-1", deployment_id="d-1"
        )

        assert project.production_url == "https://my-app.run.app"
        assert result is deployment

    async def test_does_not_update_url_when_deployment_has_no_url(self):
        project = _make_project(production_url="https://old.url")
        deployment = _make_deployment(url=None)

        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=deployment)

        project_repo = MagicMock()
        project_repo.get_by_id = AsyncMock(return_value=project)
        project_repo.update = AsyncMock(return_value=project)

        svc = _make_service(project_repo=project_repo, deployments_repo=deployments_repo)

        await svc.set_active_deployment(AsyncMock(), project_id="proj-1", deployment_id="d-1")

        # URL should remain unchanged when deployment has no URL
        assert project.production_url == "https://old.url"

    async def test_returns_deployment_even_when_project_not_found(self):
        """If project is None, still returns deployment."""
        deployment = _make_deployment(url="https://app.run.app")

        deployments_repo = MagicMock()
        deployments_repo.get_by_id = AsyncMock(return_value=deployment)

        project_repo = MagicMock()
        project_repo.get_by_id = AsyncMock(return_value=None)

        svc = _make_service(project_repo=project_repo, deployments_repo=deployments_repo)

        result = await svc.set_active_deployment(
            AsyncMock(), project_id="proj-1", deployment_id="d-1"
        )
        assert result is deployment
