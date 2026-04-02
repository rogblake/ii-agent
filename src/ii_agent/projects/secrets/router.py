"""Secrets management endpoints for projects."""

import uuid
from typing import Any

from fastapi import APIRouter

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.projects.dependencies import (
    DatabaseServiceDep,
    ProjectServiceDep,
    SecretServiceDep,
    SandboxEnvSyncServiceDep,
)
from ii_agent.projects.databases.utils import extract_db_url
from ii_agent.projects.secrets.schemas import (
    ProjectSecretsDeleteRequest,
    ProjectSecretsRequest,
    ProjectSecretsResponse,
)
from ii_agent.projects.secrets.utils import _decrypt_secrets_payload

router = APIRouter(tags=["Project Secrets"])


def _get_project_secrets(project: Any) -> dict[str, Any]:
    secrets = _decrypt_secrets_payload(project.secrets_json) or {}
    return secrets if isinstance(secrets, dict) else {}


def _build_project_secrets_response(
    *,
    project: Any,
    session_id: uuid.UUID,
    secrets: dict[str, Any],
) -> ProjectSecretsResponse:
    return ProjectSecretsResponse(
        project_id=project.id,
        session_id=session_id,
        secrets=secrets,
        updated_at=project.updated_at,
    )


@router.get("/{session_id}/secrets", response_model=ProjectSecretsResponse)
async def get_session_project_secrets(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    project_service: ProjectServiceDep,
    db: DBSession,
) -> ProjectSecretsResponse:
    """Retrieve decrypted secrets for the user's session project."""
    project = await project_service.get_session_project(
        db,
        session_id=session_id,
        user_id=current_user.id,
    )
    current_secrets = _get_project_secrets(project)
    return _build_project_secrets_response(
        project=project,
        session_id=session_id,
        secrets=current_secrets,
    )


@router.post("/{session_id}/secrets", response_model=ProjectSecretsResponse)
async def set_session_project_secrets(
    session_id: uuid.UUID,
    payload: ProjectSecretsRequest,
    current_user: CurrentUser,
    secret_service: SecretServiceDep,
    database_service: DatabaseServiceDep,
    sandbox_env_sync: SandboxEnvSyncServiceDep,
    db: DBSession,
) -> ProjectSecretsResponse:
    """Add or update secrets for the session's project."""
    database_url = payload.secrets.get("DATABASE_URL")
    if isinstance(database_url, str) and database_url:
        await database_service.upsert_database_from_url(
            db,
            session_id=session_uuid,
            connection_string=database_url,
        )

    project = await secret_service.add_secrets(
        db,
        session_id=session_id,
        user_id=current_user.id,
        secrets=payload.secrets,
    )
    current_secrets = _get_project_secrets(project)

    await sandbox_env_sync.sync_env_files(
        db,
        session_id=session_id,
        secrets=current_secrets,
        project_path=project.project_path,
        database_url=extract_db_url(project.database_json),
    )

    return _build_project_secrets_response(
        project=project,
        session_id=session_id,
        secrets=current_secrets,
    )


@router.put("/{session_id}/secrets", response_model=ProjectSecretsResponse)
async def replace_session_project_secrets(
    session_id: uuid.UUID,
    payload: ProjectSecretsRequest,
    current_user: CurrentUser,
    secret_service: SecretServiceDep,
    database_service: DatabaseServiceDep,
    sandbox_env_sync: SandboxEnvSyncServiceDep,
    db: DBSession,
) -> ProjectSecretsResponse:
    """Replace all secrets for the session's project."""
    database_url = payload.secrets.get("DATABASE_URL")
    if isinstance(database_url, str) and database_url:
        await database_service.upsert_database_from_url(
            db,
            session_id=session_id,
            connection_string=database_url,
        )

    project = await secret_service.replace_session_project_secrets(
        db,
        session_id=session_id,
        user_id=current_user.id,
        secrets=payload.secrets,
    )
    current_secrets = _get_project_secrets(project)

    await sandbox_env_sync.sync_env_files(
        db,
        session_id=session_id,
        secrets=current_secrets,
        project_path=project.project_path,
        database_url=await database_service.get_project_db_connection(
            db,
            project_id=project.id,
            user_id=current_user.id,
        ),
    )

    return _build_project_secrets_response(
        project=project,
        session_id=session_id,
        secrets=current_secrets,
    )


@router.delete("/{session_id}/secrets", response_model=ProjectSecretsResponse)
async def delete_session_project_secrets(
    session_id: uuid.UUID,
    payload: ProjectSecretsDeleteRequest,
    current_user: CurrentUser,
    secret_service: SecretServiceDep,
    sandbox_env_sync: SandboxEnvSyncServiceDep,
    db: DBSession,
) -> ProjectSecretsResponse:
    """Delete selected secrets from the session's project."""
    project = await secret_service.delete_secrets(
        db,
        session_id=session_id,
        user_id=current_user.id,
        secret_keys=payload.secret_keys,
    )
    current_secrets = _get_project_secrets(project)

    await sandbox_env_sync.sync_env_files(
        db,
        session_id=session_id,
        secrets=current_secrets,
        project_path=project.project_path,
        database_url=extract_db_url(project.database_json),
    )

    return _build_project_secrets_response(
        project=project,
        session_id=session_id,
        secrets=current_secrets,
    )
