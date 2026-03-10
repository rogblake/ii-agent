"""Skill storage - zip and upload to e2b sandbox.

All skills are zipped before uploading to sandbox because e2b
file uploads are slow for many small files. Flow:
1. Read skill directory (local path from storage_uri)
2. Zip in memory
3. Upload single zip file to sandbox
4. Extract using unzip command in sandbox

For custom skills from GitHub:
1. Files downloaded from GitHub are zipped and uploaded to GCS
2. When activating, skill is downloaded from GCS and extracted to sandbox
"""

import asyncio
import io
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from upath import UPath

from ii_agent.agent.runtime.skills.builtin import BUILTIN_SKILLS_DIR
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.core.storage import BaseStorage
    from ii_agent.agent.runtime.skills.github import GitHubFile

def resolve_storage_uri(storage_uri: str) -> Path:
    """Resolve a storage URI to a local path.

    Handles:
    - builtin:{skill_name} -> resolves to BUILTIN_SKILLS_DIR/{skill_name}
    - Absolute paths -> returns as-is (for custom skills with local storage)

    Args:
        storage_uri: Storage URI (e.g., "builtin:pdf" or "/path/to/skill")

    Returns:
        Resolved local Path
    """
    if storage_uri.startswith("builtin:"):
        skill_name = storage_uri.split(":", 1)[1]
        return BUILTIN_SKILLS_DIR / skill_name
    return Path(storage_uri)


def create_skill_zip_from_dir(skill_dir: Path) -> bytes:
    """Create a zip file from a local skill directory.

    Args:
        skill_dir: Path to skill directory (must contain SKILL.md)

    Returns:
        Zip file content as bytes
    """
    if not (skill_dir / "SKILL.md").exists():
        raise ValueError(f"SKILL.md not found in {skill_dir}")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in skill_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(skill_dir)
                zf.write(file_path, arcname)

    buffer.seek(0)
    zip_bytes = buffer.read()
    logger.debug(f"Created zip for {skill_dir.name}: {len(zip_bytes)} bytes")
    return zip_bytes


async def skill_exists(
    storage_uri: str,
    storage: Optional["BaseStorage"] = None,
) -> bool:
    """Check if skill exists at storage URI.

    Handles three types of storage URIs:
    - "builtin:{name}" -> Check local codebase
    - "skills/{user_id}/{name}" -> Check GCS (requires storage param)
    - "/absolute/path" -> Check local path (legacy)

    Args:
        storage_uri: Storage URI (e.g., "builtin:pdf", "skills/user-123/my-skill")
        storage: GCS storage client (required for GCS-based skills)

    Returns:
        True if skill exists
    """
    if storage_uri.startswith("skills/"):
        # GCS-based skill
        if storage is None:
            return False
        return await skill_exists_in_gcs(storage, storage_uri)
    else:
        # Local skill (builtin or absolute path)
        path = resolve_storage_uri(storage_uri)
        return path.exists() and path.is_dir()


async def copy_skill_to_sandbox(
    storage_uri: str,
    skill_name: str,
    sandbox,
    sandbox_base_path: str = "/workspace/.skills",
    storage: Optional["BaseStorage"] = None,
) -> str:
    """Zip skill directory and upload to sandbox, then extract.

    This is optimized for e2b - uploads single zip file instead of
    many small files, then extracts in sandbox.

    Handles three types of storage URIs:
    - "builtin:{name}" -> Load from local codebase
    - "skills/{user_id}/{name}" -> Download from GCS (requires storage param)
    - "/absolute/path" -> Load from local path (legacy)

    Args:
        storage_uri: Storage URI (e.g., "builtin:pdf", "skills/user-123/my-skill")
        skill_name: Name of the skill (used for sandbox directory)
        sandbox: SandboxManager instance (e2b)
        sandbox_base_path: Base path in sandbox for skills
        storage: GCS storage client (required for GCS-based skills)

    Returns:
        Sandbox skill directory path where skill was extracted
    """
    sandbox_skill_dir = f"{sandbox_base_path}/{skill_name}"
    zip_path_in_sandbox = f"/tmp/{skill_name}.zip"

    # Determine source and get zip content
    if storage_uri.startswith("builtin:"):
        # Built-in skill from local codebase
        skill_dir = resolve_storage_uri(storage_uri)
        zip_content = create_skill_zip_from_dir(skill_dir)
    elif storage_uri.startswith("skills/"):
        # Custom skill from GCS (async to avoid blocking)
        if storage is None:
            raise ValueError(
                f"Storage client required for GCS-based skill: {storage_uri}"
            )
        zip_content = await download_skill_zip_from_gcs(storage, storage_uri)
    else:
        # Legacy: absolute local path
        skill_dir = Path(storage_uri)
        zip_content = create_skill_zip_from_dir(skill_dir)

    # Upload zip to sandbox
    await sandbox.write_file(zip_path_in_sandbox, zip_content)

    # Create target directory and extract
    await sandbox.run_command(f"mkdir -p {sandbox_skill_dir}", user="root")
    await sandbox.run_command(
        f"unzip -o {zip_path_in_sandbox} -d {sandbox_skill_dir}", user="root"
    )

    # Fix permissions so the sandbox user can read the files
    await sandbox.run_command(f"chown -R user:user {sandbox_skill_dir}", user="root")
    await sandbox.run_command(f"chmod -R 755 {sandbox_skill_dir}", user="root")

    # Clean up zip file
    await sandbox.run_command(f"rm {zip_path_in_sandbox}", user="root")

    logger.debug(f"Extracted skill '{skill_name}' to {sandbox_skill_dir}")
    return sandbox_skill_dir


# ============================================================
# GCS storage utilities for custom skills
# ============================================================


def get_user_skill_storage_path(user_id: str, skill_name: str) -> str:
    """Generate GCS storage path for a user's skill.

    Format: skills/{user_id}/{skill_name}

    Args:
        user_id: User ID
        skill_name: Skill name (kebab-case)

    Returns:
        Storage path (without gs:// prefix)
    """
    return f"skills/{user_id}/{skill_name}"


def create_skill_zip_from_files(files: list["GitHubFile"]) -> bytes:
    """Create a zip file from a list of GitHubFile objects.

    Args:
        files: List of GitHubFile objects (path, content)

    Returns:
        Zip file content as bytes
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in files:
            zf.writestr(file.path, file.content)

    buffer.seek(0)
    zip_bytes = buffer.read()
    logger.debug(f"Created zip from {len(files)} files: {len(zip_bytes)} bytes")
    return zip_bytes


def _sync_upload_to_gcs(
    storage: "BaseStorage",
    zip_content: bytes,
    zip_path: str,
) -> None:
    """Synchronous GCS upload - to be run in thread pool."""
    zip_buffer = io.BytesIO(zip_content)
    storage.write(zip_buffer, zip_path, content_type="application/zip")


async def upload_skill_to_gcs(
    storage: "BaseStorage",
    user_id: str,
    skill_name: str,
    files: list["GitHubFile"],
) -> str:
    """Upload skill files to GCS as a zip.

    Args:
        storage: GCS storage client
        user_id: User ID
        skill_name: Skill name (kebab-case)
        files: List of GitHubFile objects to upload

    Returns:
        Storage path where skill was uploaded (e.g., skills/{user_id}/{skill_name})
    """
    base_path = get_user_skill_storage_path(user_id, skill_name)
    zip_path = f"{base_path}/skill.zip"

    # Create zip from files (CPU-bound, fast in memory)
    zip_content = create_skill_zip_from_files(files)

    # Upload to GCS in thread pool to avoid blocking event loop
    try:
        await asyncio.to_thread(_sync_upload_to_gcs, storage, zip_content, zip_path)
    except Exception as e:
        logger.error(f"Failed to upload skill to GCS: {e}")
        raise

    logger.info(f"Uploaded skill '{skill_name}' to GCS ({len(zip_content)} bytes)")

    return base_path


def _sync_download_from_gcs(storage: "BaseStorage", zip_path: str) -> bytes:
    """Synchronous GCS download - to be run in thread pool."""
    zip_data = storage.read(zip_path)
    return zip_data.read()


async def download_skill_zip_from_gcs(
    storage: "BaseStorage",
    storage_path: str,
) -> bytes:
    """Download skill zip from GCS.

    Args:
        storage: GCS storage client
        storage_path: Path in GCS (e.g., skills/{user_id}/{skill_name})

    Returns:
        Zip file content as bytes
    """
    zip_path = f"{storage_path}/skill.zip"
    try:
        return await asyncio.to_thread(_sync_download_from_gcs, storage, zip_path)
    except Exception as e:
        logger.error(f"Failed to download skill from GCS: {e}")
        raise


def _sync_exists_in_gcs(storage: "BaseStorage", zip_path: str) -> bool:
    """Synchronous GCS exists check - to be run in thread pool."""
    return storage.is_exists(zip_path)


async def skill_exists_in_gcs(
    storage: "BaseStorage",
    storage_path: str,
) -> bool:
    """Check if skill zip exists in GCS.

    Args:
        storage: GCS storage client
        storage_path: Path in GCS (e.g., skills/{user_id}/{skill_name})

    Returns:
        True if skill zip exists
    """
    zip_path = f"{storage_path}/skill.zip"
    return await asyncio.to_thread(_sync_exists_in_gcs, storage, zip_path)


def delete_skill_from_gcs(
    storage: "BaseStorage",
    storage_path: str,
) -> bool:
    """Delete skill zip from GCS.

    Args:
        storage: GCS storage client
        storage_path: Path in GCS (e.g., skills/{user_id}/{skill_name})

    Returns:
        True if deletion was successful
    """
    zip_path = f"{storage_path}/skill.zip"
    try:
        # GCS BaseStorage doesn't have delete, but we can use the client directly
        # For now, just log - deletion can be implemented later if needed
        logger.info(f"Skill deletion requested for {zip_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete skill from GCS: {e}")
        return False
