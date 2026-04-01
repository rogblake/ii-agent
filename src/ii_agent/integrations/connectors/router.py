"""API endpoints for external service connectors.

This module provides a clean, extensible API for managing external service
connectors using the abstract base class architecture.
"""

import logging
from typing import Optional

from fastapi import APIRouter
from itsdangerous import URLSafeSerializer
from pydantic import BaseModel

from ii_agent.core.config.settings import get_settings
from ii_agent.integrations.connectors.composio.router import router as composio_router
from ii_agent.integrations.connectors import ConnectorType, ConnectorFactory
from ii_agent.integrations.connectors.exceptions import (
    ConnectorNotFoundError,
    ConnectorConfigError,
    ConnectorStateError,
)
from ii_agent.integrations.connectors.github import GitHubConnector
from ii_agent.integrations.connectors.google_drive import GoogleDriveConnector
from ii_agent.integrations.connectors.revenuecat import RevenueCatConnector
from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.core.storage.dependencies import StorageServiceDep
from ii_agent.core.storage.path_resolver import path_resolver
from ii_agent.files.types import AssetType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/connectors", tags=["Connectors"])
router.include_router(composio_router)


# Response Models
class ConnectorAuthUrlResponse(BaseModel):
    """Response model for connector authentication URL."""

    auth_url: str
    state: str


class ConnectorCallbackRequest(BaseModel):
    """Request model for OAuth callback."""

    code: str
    state: str
    redirect_uri: Optional[str] = None


class ConnectorStatusResponse(BaseModel):
    """Response model for connector status."""

    is_connected: bool
    connector_type: str
    metadata: Optional[dict] = None
    access_token: Optional[str] = None


class GoogleDriveFilePickRequest(BaseModel):
    """Request model for Google Drive file selection."""

    file_ids: list[str]


class GoogleDrivePickerConfigResponse(BaseModel):
    """Response model for Google Drive picker configuration."""

    is_connected: bool
    access_token: Optional[str] = None
    developer_key: Optional[str] = None
    app_id: Optional[str] = None


class GitHubAppConfigResponse(BaseModel):
    """Response model for GitHub App configuration."""

    app_name: Optional[str] = None
    installation_url: Optional[str] = None


class GitHubRepository(BaseModel):
    """Response model for GitHub repository."""

    id: int
    name: str
    full_name: str
    owner: str
    private: bool
    description: Optional[str] = None
    html_url: str
    default_branch: str


class GitHubRepositoriesResponse(BaseModel):
    """Response model for list of GitHub repositories."""

    repositories: list[GitHubRepository]


def _create_state_token(
    user_id: str,
    connector_type: str,
    frontend_url: Optional[str] = None,
    redirect_uri: Optional[str] = None,
    code_verifier: Optional[str] = None,
) -> str:
    """Create encrypted state token for OAuth flow.

    Args:
        user_id: User ID for state validation
        connector_type: Type of connector
        frontend_url: Optional frontend URL for redirect
        redirect_uri: Optional OAuth redirect URI for multi-domain support
        code_verifier: Optional PKCE code verifier to persist across the flow

    Returns:
        str: Encrypted state token
    """
    serializer = URLSafeSerializer(get_settings().oauth.session_secret_key)
    state_data = {
        "user_id": user_id,
        "connector": connector_type,
    }
    if frontend_url:
        state_data["frontend_url"] = frontend_url
    if redirect_uri:
        state_data["redirect_uri"] = redirect_uri
    if code_verifier:
        state_data["code_verifier"] = code_verifier
    return serializer.dumps(state_data)


def _verify_state_token(state: str, expected_user_id: str) -> dict:
    """Verify and decode state token.

    Args:
        state: State token to verify
        expected_user_id: Expected user ID in state

    Returns:
        dict: Decoded state data

    Raises:
        ConnectorStateError: If state is invalid or user ID doesn't match
    """
    serializer = URLSafeSerializer(get_settings().oauth.session_secret_key)
    try:
        state_data = serializer.loads(state)
        if state_data.get("user_id") != expected_user_id:
            raise ConnectorStateError("Invalid state parameter")
        return state_data
    except ConnectorStateError:
        raise
    except Exception as e:
        logger.error(f"State verification failed: {e}")
        raise ConnectorStateError("Invalid state parameter") from e


# Google Drive Endpoints
@router.get("/google-drive/auth-url", response_model=ConnectorAuthUrlResponse)
async def get_google_drive_auth_url(
    db: DBSession,
    current_user: CurrentUser,
    frontend_url: Optional[str] = None,
) -> ConnectorAuthUrlResponse:
    """Generate Google Drive OAuth URL."""
    try:
        connector = ConnectorFactory.create(ConnectorType.GOOGLE_DRIVE, db)
        state = _create_state_token(current_user.id, "google_drive", frontend_url)
        auth_url = await connector.get_auth_url(state)

        return ConnectorAuthUrlResponse(auth_url=auth_url, state=state)
    except ValueError as e:
        raise ConnectorConfigError(str(e)) from e


@router.post("/google-drive/callback")
async def google_drive_callback(
    request: ConnectorCallbackRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Handle Google Drive OAuth callback."""
    _verify_state_token(request.state, current_user.id)

    connector = ConnectorFactory.create(ConnectorType.GOOGLE_DRIVE, db)
    connector_data = await connector.handle_callback(request.code, request.state)
    await connector.connect(current_user.id, connector_data)

    return {"success": True, "message": "Google Drive connected successfully"}


@router.get("/google-drive/status", response_model=ConnectorStatusResponse)
async def get_google_drive_status(
    db: DBSession,
    current_user: CurrentUser,
) -> ConnectorStatusResponse:
    """Check if user has connected Google Drive."""
    connector = ConnectorFactory.create(ConnectorType.GOOGLE_DRIVE, db)
    status = await connector.get_status(current_user.id)

    return ConnectorStatusResponse(
        is_connected=status.is_connected,
        connector_type=status.connector_type,
        metadata=status.metadata,
        access_token=status.access_token,
    )


@router.get(
    "/google-drive/picker-config",
    response_model=GoogleDrivePickerConfigResponse,
)
async def get_google_drive_picker_config(
    db: DBSession,
    current_user: CurrentUser,
) -> GoogleDrivePickerConfigResponse:
    """Return configuration required to launch the Google Drive picker."""
    connector = ConnectorFactory.create(ConnectorType.GOOGLE_DRIVE, db)

    if not isinstance(connector, GoogleDriveConnector):
        raise ConnectorConfigError("Invalid connector type")

    picker_config = await connector.get_picker_config(current_user.id)

    return GoogleDrivePickerConfigResponse(**picker_config)


@router.post("/google-drive/files")
async def download_google_drive_files(
    request: GoogleDriveFilePickRequest,
    db: DBSession,
    current_user: CurrentUser,
    storage: StorageServiceDep,
):
    """Download selected files from Google Drive.

    Note: This endpoint maintains the original implementation for file operations.
    The file download logic is connector-specific and kept in the route for now.
    """
    from datetime import datetime, timezone
    from io import BytesIO

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    from sqlalchemy import select

    from ii_agent.files import FileAsset

    connector = ConnectorFactory.create(ConnectorType.GOOGLE_DRIVE, db)

    if not isinstance(connector, GoogleDriveConnector):
        raise ConnectorConfigError("Invalid connector type")

    credentials = await connector.get_credentials(current_user.id)
    if not credentials:
        raise ConnectorNotFoundError("Google Drive is not connected")

    service = build("drive", "v3", credentials=credentials)
    downloaded_files = []

    def list_files_in_folder(folder_id: str) -> list:
        """Recursively list all files in a folder."""
        file_ids = []
        page_token = None

        while True:
            try:
                results = (
                    service.files()
                    .list(
                        q=f"'{folder_id}' in parents and trashed=false",
                        fields="nextPageToken, files(id, name, mimeType)",
                        pageToken=page_token,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    )
                    .execute()
                )

                items = results.get("files", [])
                for item in items:
                    if item.get("mimeType") == "application/vnd.google-apps.folder":
                        file_ids.extend(list_files_in_folder(item["id"]))
                    else:
                        file_ids.append(item["id"])

                page_token = results.get("nextPageToken")
                if not page_token:
                    break

            except Exception as e:
                logger.error(f"Failed to list files in folder {folder_id}: {e}")
                break

        return file_ids

    folder_file_mapping = {}

    for file_id in request.file_ids:
        try:
            logger.info(f"Attempting to get metadata for file ID: {file_id}")
            file_metadata = (
                service.files()
                .get(
                    fileId=file_id,
                    fields="id,name,mimeType,size",
                    supportsAllDrives=True,
                )
                .execute()
            )
            logger.info(f"File metadata retrieved: {file_metadata}")

            is_folder = (
                file_metadata.get("mimeType")
                == "application/vnd.google-apps.folder"
            )
            logger.info(f"File {file_metadata.get('name')} is_folder: {is_folder}")

            if is_folder:
                logger.info(f"Listing files in folder: {file_metadata.get('name')}")
                folder_file_ids = list_files_in_folder(file_id)
                logger.info(f"Found {len(folder_file_ids)} files in folder")

                folder_file_mapping[file_id] = {
                    "folder_name": file_metadata["name"],
                    "folder_id": file_id,
                    "file_ids": folder_file_ids,
                    "file_uploads": [],
                }
            else:
                folder_file_mapping[file_id] = {
                    "folder_name": None,
                    "folder_id": None,
                    "file_ids": [file_id],
                    "file_uploads": [],
                }

        except Exception as e:
            logger.error(f"Failed to get metadata for file {file_id}: {e}")
            continue

    for original_id, folder_info in folder_file_mapping.items():
        for file_id in folder_info["file_ids"]:
            try:
                file_metadata = (
                    service.files()
                    .get(
                        fileId=file_id,
                        fields="id,name,mimeType,size",
                        supportsAllDrives=True,
                    )
                    .execute()
                )

                request_obj = service.files().get_media(
                    fileId=file_id, supportsAllDrives=True
                )

                fh = BytesIO()
                downloader = MediaIoBaseDownload(fh, request_obj)
                done = False
                while not done:
                    status, done = downloader.next_chunk()

                ext = file_metadata['name'].rsplit('.', 1)[-1] if '.' in file_metadata['name'] else 'bin'
                asset_type = AssetType.from_content_type(file_metadata.get("mimeType"))
                storage_path = path_resolver.user_file(current_user.id, asset_type, file_id, ext)
                fh.seek(0)
                await storage.write(storage_path, fh, file_metadata.get("mimeType"))

                file_upload = FileAsset(
                    user_id=current_user.id,
                    file_name=file_metadata["name"],
                    file_size=int(file_metadata.get("size", 0)),
                    storage_path=storage_path,
                    content_type=file_metadata.get("mimeType"),
                )
                db.add(file_upload)
                await db.flush()

                folder_info["file_uploads"].append(file_upload.id)

            except Exception as e:
                logger.error(f"Failed to download file {file_id}: {e}")
                continue

    for original_id, folder_info in folder_file_mapping.items():
        if not folder_info["file_uploads"]:
            continue

        if folder_info["folder_name"]:
            downloaded_files.append({
                "id": ",".join(str(fid) for fid in folder_info["file_uploads"]),
                "name": folder_info["folder_name"],
                "size": 0,
                "mime_type": "application/vnd.google-apps.folder",
                "file_url": None,
                "is_folder": True,
                "file_ids": folder_info["file_uploads"],
                "file_count": len(folder_info["file_uploads"])
            })
        else:
            file_upload_id = folder_info["file_uploads"][0]
            result = await db.execute(
                select(FileAsset).where(FileAsset.id == file_upload_id)
            )
            file_upload = result.scalar_one()

            downloaded_files.append(
                {
                    "id": str(file_upload.id),
                    "name": file_upload.file_name,
                    "size": file_upload.file_size,
                    "mime_type": file_upload.content_type,
                    "file_url": await storage.signed_download_url(
                        file_upload.storage_path
                    ),
                    "is_folder": False,
                }
            )

    await db.commit()

    return {"success": True, "files": downloaded_files}


@router.delete("/google-drive")
async def disconnect_google_drive(
    db: DBSession,
    current_user: CurrentUser,
):
    """Disconnect Google Drive and revoke access token."""
    connector = ConnectorFactory.create(ConnectorType.GOOGLE_DRIVE, db)

    if not await connector.get_connector(current_user.id):
        raise ConnectorNotFoundError("Google Drive is not connected")

    await connector.disconnect(current_user.id)
    return {"success": True, "message": "Google Drive disconnected successfully"}


# GitHub Endpoints
@router.get("/github/auth-url", response_model=ConnectorAuthUrlResponse)
async def get_github_auth_url(
    db: DBSession,
    current_user: CurrentUser,
    redirect_uri: Optional[str] = None,
) -> ConnectorAuthUrlResponse:
    """Generate GitHub OAuth URL.

    Args:
        redirect_uri: Optional OAuth redirect URI for multi-domain support.
                     If not provided, uses server-side config.
    """
    try:
        connector = ConnectorFactory.create(ConnectorType.GITHUB, db)
        state = _create_state_token(current_user.id, "github", redirect_uri=redirect_uri)

        if not isinstance(connector, GitHubConnector):
            raise ConnectorConfigError("Invalid connector type")

        auth_url = await connector.get_auth_url(state, redirect_uri=redirect_uri)

        return ConnectorAuthUrlResponse(auth_url=auth_url, state=state)
    except ValueError as e:
        raise ConnectorConfigError(str(e)) from e


@router.post("/github/callback")
async def github_callback(
    request: ConnectorCallbackRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Handle GitHub OAuth callback."""
    state_data = _verify_state_token(request.state, current_user.id)

    # Use redirect_uri from request, or fall back to state token
    redirect_uri = request.redirect_uri or state_data.get("redirect_uri")

    connector = ConnectorFactory.create(ConnectorType.GITHUB, db)

    if not isinstance(connector, GitHubConnector):
        raise ConnectorConfigError("Invalid connector type")

    connector_data = await connector.handle_callback(
        request.code, request.state, redirect_uri=redirect_uri
    )
    await connector.connect(current_user.id, connector_data)

    return {"success": True, "message": "GitHub connected successfully"}


@router.get("/github/status", response_model=ConnectorStatusResponse)
async def get_github_status(
    db: DBSession,
    current_user: CurrentUser,
) -> ConnectorStatusResponse:
    """Get GitHub connection status."""
    connector = ConnectorFactory.create(ConnectorType.GITHUB, db)
    status = await connector.get_status(current_user.id)

    return ConnectorStatusResponse(
        is_connected=status.is_connected,
        connector_type=status.connector_type,
        metadata=status.metadata,
        access_token=status.access_token,
    )


@router.delete("/github")
async def disconnect_github(
    db: DBSession,
    current_user: CurrentUser,
):
    """Disconnect GitHub."""
    connector = ConnectorFactory.create(ConnectorType.GITHUB, db)

    if not await connector.get_connector(current_user.id):
        raise ConnectorNotFoundError("GitHub is not connected")

    await connector.disconnect(current_user.id)
    return {"success": True, "message": "GitHub disconnected successfully"}


@router.get("/github/app-config", response_model=GitHubAppConfigResponse)
async def get_github_app_config(
    db: DBSession,
) -> GitHubAppConfigResponse:
    """Get GitHub App configuration for installation."""
    connector = ConnectorFactory.create(ConnectorType.GITHUB, db)

    if not isinstance(connector, GitHubConnector):
        raise ConnectorConfigError("Invalid connector type")

    app_config = await connector.get_app_config()

    return GitHubAppConfigResponse(**app_config)


@router.get("/github/repositories", response_model=GitHubRepositoriesResponse)
async def get_github_repositories(
    db: DBSession,
    current_user: CurrentUser,
) -> GitHubRepositoriesResponse:
    """Get list of GitHub repositories the user has access to."""
    connector = ConnectorFactory.create(ConnectorType.GITHUB, db)

    if not isinstance(connector, GitHubConnector):
        raise ConnectorConfigError("Invalid connector type")

    repos_data = await connector.get_repositories(current_user.id)

    repositories = [
        GitHubRepository(
            id=repo["id"],
            name=repo["name"],
            full_name=repo["full_name"],
            owner=repo["owner"]["login"],
            private=repo["private"],
            description=repo.get("description"),
            html_url=repo["html_url"],
            default_branch=repo.get("default_branch", "main"),
        )
        for repo in repos_data
    ]

    logger.info(
        f"Successfully fetched {len(repositories)} repositories for user {current_user.id}"
    )
    return GitHubRepositoriesResponse(repositories=repositories)


# RevenueCat Endpoints
@router.get("/revenuecat/auth-url", response_model=ConnectorAuthUrlResponse)
async def get_revenuecat_auth_url(
    db: DBSession,
    current_user: CurrentUser,
    redirect_uri: Optional[str] = None,
) -> ConnectorAuthUrlResponse:
    """Generate RevenueCat OAuth URL."""
    try:
        connector = ConnectorFactory.create(ConnectorType.REVENUECAT, db)

        if not isinstance(connector, RevenueCatConnector):
            raise ConnectorConfigError("Invalid connector type")

        # Generate PKCE pair and embed code_verifier in the signed state token
        code_verifier, code_challenge = RevenueCatConnector.generate_pkce()
        state = _create_state_token(
            current_user.id,
            "revenuecat",
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )

        auth_url = await connector.get_auth_url(
            state, redirect_uri=redirect_uri, code_challenge=code_challenge
        )
        return ConnectorAuthUrlResponse(auth_url=auth_url, state=state)
    except ValueError as e:
        raise ConnectorConfigError(str(e)) from e


@router.post("/revenuecat/callback")
async def revenuecat_callback(
    request: ConnectorCallbackRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Handle RevenueCat OAuth callback."""
    state_data = _verify_state_token(request.state, current_user.id)
    redirect_uri = request.redirect_uri or state_data.get("redirect_uri")
    code_verifier = state_data.get("code_verifier")

    connector = ConnectorFactory.create(ConnectorType.REVENUECAT, db)
    if not isinstance(connector, RevenueCatConnector):
        raise ConnectorConfigError("Invalid connector type")

    connector_data = await connector.handle_callback(
        request.code,
        request.state,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
    )
    await connector.connect(current_user.id, connector_data)

    return {"success": True, "message": "RevenueCat connected successfully"}


@router.get("/revenuecat/status", response_model=ConnectorStatusResponse)
async def get_revenuecat_status(
    db: DBSession,
    current_user: CurrentUser,
) -> ConnectorStatusResponse:
    """Get RevenueCat connection status."""
    connector = ConnectorFactory.create(ConnectorType.REVENUECAT, db)
    status = await connector.get_status(current_user.id)

    return ConnectorStatusResponse(
        is_connected=status.is_connected,
        connector_type=status.connector_type,
        metadata=status.metadata,
        access_token=status.access_token,
    )


@router.delete("/revenuecat")
async def disconnect_revenuecat(
    db: DBSession,
    current_user: CurrentUser,
):
    """Disconnect RevenueCat."""
    connector = ConnectorFactory.create(ConnectorType.REVENUECAT, db)

    if not await connector.get_connector(current_user.id):
        raise ConnectorNotFoundError("RevenueCat is not connected")

    await connector.disconnect(current_user.id)
    return {"success": True, "message": "RevenueCat disconnected successfully"}
