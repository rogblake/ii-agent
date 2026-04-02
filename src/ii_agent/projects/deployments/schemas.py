from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field


class ProjectDeploymentResponse(BaseModel):
    """Current deployment information for a project."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    project_id: str
    provider: Optional[str] = None
    deployment_url: Optional[str] = None
    deployment_status: Optional[str] = None
    version: Optional[int] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_deployment(self) -> bool:
        return self.id is not None