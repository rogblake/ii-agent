"""Secrets management endpoints for projects."""

import uuid

from fastapi import APIRouter

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.projects.dependencies import (
    ProjectServiceDep,
    SecretServiceDep,
    SandboxEnvSyncServiceDep,
)
from ii_agent.projects.databases.utils import extract_db_url
from ii_agent.projects.secrets.schemas import ProjectSecretsRequest, ProjectSecretsResponse
from ii_agent.projects.secrets.utils import _decrypt_secrets_payload

router = APIRouter(tags=["Project Secrets"])


@router.get("/{session_id}/secrets", response_model=ProjectSecretsResponse)
async def get_session_project_secrets(
    session_id: str,
    current_user: CurrentUser,
    project_service: ProjectServiceDep,
    db: DBSession,
) -> ProjectSecretsResponse:
    """Retrieve decrypted secrets for the user's session project."""
    project = await project_service.get_session_project(
        db,
        session_id=session_id,
        user_id=str(current_user.id),
    )
    return ProjectSecretsResponse(
        project_id=project.id,
        session_id=session_id,
        secrets=_decrypt_secrets_payload(project.secrets_json) or {},
        updated_at=project.updated_at,
    )


@router.post("/{session_id}/secrets", response_model=ProjectSecretsResponse)
async def set_session_project_secrets(
    session_id: str,
    payload: ProjectSecretsRequest,
    current_user: CurrentUser,
    secret_service: SecretServiceDep,
    sandbox_env_sync: SandboxEnvSyncServiceDep,
    db: DBSession,
) -> ProjectSecretsResponse:
    """Replace the secrets JSON for the session's project with the provided payload."""

    project = await secret_service.replace_session_project_secrets(
        db,
        session_id=session_id,
        user_id=str(current_user.id),
        secrets=payload.secrets,
    )
    # Sync .env and .user_env.sh files in the sandbox
    await sandbox_env_sync.sync_env_files(
        db,
        session_id=uuid.UUID(session_id),
        secrets=payload.secrets,
        project_path=project.project_path,
        database_url=extract_db_url(project.database_json),
    )

    return ProjectSecretsResponse(
        project_id=project.id,
        session_id=session_id,
        secrets=_decrypt_secrets_payload(project.secrets_json) or {},
        updated_at=project.updated_at,
    )
