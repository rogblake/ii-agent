from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field

from ii_agent.projects.deployments.types import DeploymentProvider, DeploymentStatus


class ProjectDeploymentResponse(BaseModel):
    """Full deployment information returned by the service layer."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = None
    project_id: UUID
    deployed_by_user_id: Optional[UUID] = None
    provider: Optional[DeploymentProvider] = None
    environment: Optional[str] = None
    version: Optional[int] = None
    deployment_status: Optional[DeploymentStatus] = None
    deployment_url: Optional[str] = None
    source_path: Optional[str] = None
    snapshot_id: Optional[str] = None
    error_message: Optional[str] = None
    error_phase: Optional[str] = None
    error_details: Optional[dict[str, Any]] = None
    deploy_metadata: Optional[dict[str, Any]] = None
    upload_duration_ms: Optional[int] = None
    build_duration_ms: Optional[int] = None
    started_at: Optional[datetime] = None
    deployed_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_deployment(self) -> bool:
        return self.id is not None