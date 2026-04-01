"""Project endpoints for retrieving session project metadata."""

import uuid

from fastapi import APIRouter

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.projects.dependencies import ProjectServiceDep
from ii_agent.projects.schemas import SessionProjectResponse

from ii_agent.projects.databases.router import router as database_router
from ii_agent.projects.secrets.router import router as secrets_router
from ii_agent.projects.deployments.router import router as deployment_router
from ii_agent.projects.design.router import router as design_router
from ii_agent.projects.subdomains.router import router as subdomains_router

router = APIRouter(prefix="/project", tags=["Project"])
router.include_router(database_router)
router.include_router(secrets_router)
router.include_router(deployment_router)
router.include_router(design_router)
router.include_router(subdomains_router)


@router.get("/{session_id}", response_model=SessionProjectResponse)
async def get_session_project(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    project_service: ProjectServiceDep,
    db: DBSession,
) -> SessionProjectResponse:
    """Return the project metadata associated with a session for the current user."""
    project = await project_service.get_session_project(
        db,
        session_id=session_id,
        user_id=current_user.id,
    )
    return SessionProjectResponse.model_validate(project)
