"""Deployment endpoints for projects."""

from fastapi import APIRouter

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.projects.deployments.dependencies import DeploymentsServiceDep
from ii_agent.projects.deployments.exceptions import DeploymentNotFoundError
from ii_agent.projects.deployments.schemas import ProjectDeploymentResponse

router = APIRouter(tags=["Project Deployments"])


@router.get(
    "/{project_id}/deployment",
    response_model=ProjectDeploymentResponse,
)
async def get_project_deployment(
    project_id: str,
    current_user: CurrentUser,
    deployments_service: DeploymentsServiceDep,
    db: DBSession,
) -> ProjectDeploymentResponse:
    """Get the current deployment information for a project.

    Returns deployment details including provider type, which is needed
    to determine if subdomain claiming is available (Cloud Run only).
    """
    # Verify the user owns this project before returning deployment info
    try:
        deployment = await deployments_service.get_project_deployment(
            db,
            user_id=str(current_user.id),
            project_id=project_id,
        )
    except DeploymentNotFoundError:
        return ProjectDeploymentResponse(project_id=project_id)

    return deployment
