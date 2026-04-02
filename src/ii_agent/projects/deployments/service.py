from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.projects.deployments.exceptions import DeploymentNotFoundError
from ii_agent.projects.deployments.models import ProjectDeployment
from ii_agent.projects.deployments.repository import DeploymentsRepository
from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.projects.exceptions import ProjectNotFoundError
from ii_agent.projects.repository import ProjectRepository


class DeploymentsService:
    def __init__(
        self,
        *,
        project_repo: ProjectRepository,
        deployments_repo: DeploymentsRepository,
        config: Settings,
    ) -> None:
        self._config = config
        self._project_repo = project_repo
        self._deployments_repo = deployments_repo

    async def get_project_deployment(
        self,
        db: AsyncSession,
        user_id: str,
        project_id: str,
    ) -> ProjectDeployment:
        """Get the current deployment information for a project.

        Returns deployment details including provider type, which is needed
        to determine if subdomain claiming is available (Cloud Run only).
        """
        project = await self._project_repo.get_by_id_and_user(
            db,
            project_id=project_id,
            user_id=user_id,
        )
        if not project:
            raise ProjectNotFoundError(project_id)

        deployment = await self._deployments_repo.get_latest_deployment(
            db,
            project_id=project_id,
            provider=None,
        )

        if not deployment:
            raise DeploymentNotFoundError(project_id)

        return deployment

    async def create_deployment(
        self,
        db: AsyncSession,
        *,
        project_id: str,
        user_id: str,
        provider: str,
        environment: str = "production",
        source_path: Optional[str] = None,
        snapshot_id: Optional[str] = None,
    ) -> ProjectDeployment:
        """Create a new deployment record with auto-incrementing version."""
        max_version = await self._deployments_repo.get_max_version(db, project_id)

        deployment = ProjectDeployment(
            id=str(uuid.uuid4()),
            project_id=project_id,
            deployed_by_user_id=user_id,
            provider=provider,
            environment=environment,
            source_path=source_path,
            snapshot_id=snapshot_id,
            version=max_version + 1,
            deployment_status="pending",
            started_at=datetime.now(timezone.utc),
        )

        return await self._deployments_repo.create(db, deployment)

    async def update_deployment_status(
        self,
        db: AsyncSession,
        *,
        deployment_id: str,
        status: str,
        deployment_url: Optional[str] = None,
        error_message: Optional[str] = None,
        error_phase: Optional[str] = None,
        error_details: Optional[dict] = None,
    ) -> Optional[ProjectDeployment]:
        """Update deployment status and optional error/url fields."""
        deployment = await self._deployments_repo.get_by_id(db, deployment_id)
        if not deployment:
            return None

        deployment.deployment_status = status

        if deployment_url is not None:
            deployment.deployment_url = deployment_url
        if error_message is not None:
            deployment.error_message = error_message
        if error_phase is not None:
            deployment.error_phase = error_phase
        if error_details is not None:
            deployment.error_details = error_details

        now = datetime.now(timezone.utc)
        if status == "deployed":
            deployment.deployed_at = now
            deployment.finished_at = now
        elif status == "failed":
            deployment.finished_at = now

        return await self._deployments_repo.update(db, deployment)

    async def update_deployment_metadata(
        self,
        db: AsyncSession,
        *,
        deployment_id: str,
        metadata: Optional[dict[str, Any]] = None,
        upload_duration_ms: Optional[int] = None,
        build_duration_ms: Optional[int] = None,
    ) -> Optional[ProjectDeployment]:
        """Update deployment metadata and performance metrics."""
        deployment = await self._deployments_repo.get_by_id(db, deployment_id)
        if not deployment:
            return None

        if metadata is not None:
            deployment.deploy_metadata = {
                **(deployment.deploy_metadata or {}),
                **metadata,
            }
        if upload_duration_ms is not None:
            deployment.upload_duration_ms = upload_duration_ms
        if build_duration_ms is not None:
            deployment.build_duration_ms = build_duration_ms

        return await self._deployments_repo.update(db, deployment)

    async def set_active_deployment(
        self,
        db: AsyncSession,
        *,
        project_id: str,
        deployment_id: str,
    ) -> Optional[ProjectDeployment]:
        """Mark a deployment as the active one for its project.

        Updates the project's production_url to the deployment's URL.
        """
        deployment = await self._deployments_repo.get_by_id(db, deployment_id)
        if not deployment:
            return None

        project = await self._project_repo.get_by_id(db, project_id)
        if project and deployment.deployment_url:
            project.production_url = deployment.deployment_url
            await self._project_repo.update(db, project)

        return deployment
