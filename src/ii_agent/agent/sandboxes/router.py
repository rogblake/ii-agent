"""API routes for sandboxes domain."""

from __future__ import annotations

import posixpath
import uuid

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ii_agent.agent.sandboxes.dependencies import SandboxServiceDep
from ii_agent.agent.sandboxes.e2b import E2BSandboxManager
from ii_agent.agent.sandboxes.schemas import SandboxStatus, guess_mime_type, is_image_file_path
from ii_agent.auth.dependencies import CurrentUser
from ii_agent.core.dependencies import DBSession
from ii_agent.core.exceptions import ServiceUnavailableError, ValidationError
from ii_agent.sessions.dependencies import SessionRepositoryDep, SessionServiceDep
from ii_agent.sessions.exceptions import SessionNotFoundError

router = APIRouter(prefix="/sandbox-files", tags=["Sandboxes"])


def _normalize_sandbox_path(file_path: str) -> str:
    normalized = posixpath.normpath(file_path.strip())
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


def _is_path_within_root(file_path: str, root_path: str) -> bool:
    normalized_path = _normalize_sandbox_path(file_path)
    normalized_root = _normalize_sandbox_path(root_path)
    return normalized_path == normalized_root or normalized_path.startswith(
        f"{normalized_root.rstrip('/')}/"
    )


@router.get("/{session_id}/preview")
async def preview_sandbox_file(
    session_id: str,
    current_user: CurrentUser,
    sandbox_service: SandboxServiceDep,
    session_repo: SessionRepositoryDep,
    session_service: SessionServiceDep,
    db: DBSession,
    path: str = Query(..., description="Absolute file path inside the sandbox"),
) -> StreamingResponse:
    """Stream an image file from a session sandbox for explorer previews."""

    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise ValidationError("Invalid session id") from exc

    session = await session_repo.get_by_id_and_user(db, session_id, str(current_user.id))
    if not session:
        raise SessionNotFoundError("Session not found or access denied")

    normalized_path = _normalize_sandbox_path(path)
    workspace_root = (
        session.project.project_path
        if session.project is not None and session.project.project_path
        else "/workspace"
    )
    if not _is_path_within_root(normalized_path, workspace_root):
        raise ValidationError("Path must stay within the sandbox workspace")

    if not is_image_file_path(normalized_path):
        raise ValidationError("Preview is only available for image files")

    sandbox_record = await sandbox_service.resolve_sandbox_for_session(
        db,
        session_uuid,
        session_service=session_service,
    )
    if not sandbox_record or not sandbox_record.provider_sandbox_id:
        raise ServiceUnavailableError("No active sandbox is available for this session")

    sandbox_manager = await E2BSandboxManager.from_sandbox_record(sandbox_record)
    if not sandbox_manager:
        raise ServiceUnavailableError("Could not connect to the sandbox")

    sandbox_info = await sandbox_manager.get_info()
    if sandbox_info.status != SandboxStatus.RUNNING:
        raise ServiceUnavailableError("Sandbox is not running")

    file_stream = await sandbox_manager.download_file_stream(normalized_path)
    filename = posixpath.basename(normalized_path) or "preview"

    return StreamingResponse(
        file_stream,
        media_type=guess_mime_type(normalized_path) or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
