from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, List, Optional, Tuple

import httpx

from ii_agent.core.logger import logger
from ii_agent.agent.sandboxes import E2BSandboxManager, SandboxManager
from ii_agent.agent.sandboxes.base import FileUpload, SandboxStatus
from ii_agent.agent.runtime.media import File, Image

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer
    from ii_agent.agent.runtime.run.agent import RunInput


class SandboxProvider:
    """Manages sandbox lifecycle and media uploads."""

    def __init__(
        self,
        session_id: str,
        user_id: str,
        lock: asyncio.Lock,
        container: ServiceContainer,
    ):
        self._session_id = session_id
        self._user_id = user_id
        self._lock = lock
        self._container = container
        self._sandbox: Optional[SandboxManager] = None
        self._was_initialized: Optional[bool] = None

    async def init_sandbox(self) -> SandboxManager:
        """Get or create the sandbox for this agent's session.

        Uses double-check locking to prevent concurrent initialization.

        Returns:
            The sandbox manager instance ready for use.
        """
        from ii_agent.core.db.manager import get_db_session_local

        if self._sandbox is None or (
            await self._sandbox.get_status() == SandboxStatus.NOT_INITIALIZED
        ):
            async with self._lock:
                if self._sandbox is None or (
                    await self._sandbox.get_status() == SandboxStatus.NOT_INITIALIZED
                ):
                    self._sandbox = await E2BSandboxManager.init(
                        session_id=self._session_id,
                        mcp_setting_service=self._container.mcp_setting_service,
                        composio_service=self._container.composio_service,
                    )
                    await self._sandbox.configure_sandbox_mcp(self._user_id)
                    self._was_initialized = True

                    async with get_db_session_local() as db:
                        await self._container.session_service.update_sandbox_id(
                            db, self._session_id, self._sandbox.sandbox_id
                        )

        return self._sandbox

    @property
    def sandbox(self) -> Optional[SandboxManager]:
        """Get the sandbox manager (may not be initialized yet)."""
        return self._sandbox

    @sandbox.setter
    def sandbox(self, value: Optional[SandboxManager]) -> None:
        """Set the sandbox manager."""
        self._sandbox = value

    @property
    def was_initialized(self) -> Optional[bool]:
        """Check if sandbox was just initialized this run."""
        return self._was_initialized

    def clear_initialized_flag(self) -> None:
        """Clear the initialization flag after yielding the event."""
        self._was_initialized = None

    async def upload_media(
        self,
        sandbox: SandboxManager,
        run_input: RunInput,
        upload_path: str,
    ) -> Tuple[List[File], List[Image]]:
        """Download and upload files/images to sandbox.

        Args:
            sandbox: The sandbox manager to upload to.
            run_input: The run input containing files and images.
            upload_path: The path in sandbox to upload files to.

        Returns:
            Tuple of (sandbox_files, sandbox_images) with updated paths.
        """
        files = list(run_input.files) if run_input.files else []
        images = list(run_input.images) if run_input.images else []

        if not files and not images:
            return [], []

        async def download_file(
            client: httpx.AsyncClient, file: File
        ) -> Optional[Tuple[str, str, bytes, str]]:
            if not file.url:
                return None
            try:
                response = await client.get(file.url)
                response.raise_for_status()
                filename = file.filename or f"file_{file.id}"
                return (file.id or "", f"{upload_path}/{filename}", response.content, "file")
            except Exception as e:
                logger.warning(f"Failed to download file {file.filename}: {e}")
                return None

        async def download_image(
            client: httpx.AsyncClient, image: Image, index: int
        ) -> Optional[Tuple[Image, str, bytes, str]]:
            if not image.url:
                return None
            try:
                response = await client.get(image.url)
                response.raise_for_status()
                ext = "png"
                if image.mime_type:
                    ext = image.mime_type.split("/")[-1]
                elif image.format:
                    ext = image.format
                filename = f"image_{index}.{ext}"
                filepath = f"{upload_path}/{filename}"
                return (image, filepath, response.content, "image")
            except Exception as e:
                logger.warning(f"Failed to download image: {e}")
                return None

        async with httpx.AsyncClient() as client:
            file_tasks = [download_file(client, f) for f in files]
            image_tasks = [download_image(client, img, i) for i, img in enumerate(images)]
            results = await asyncio.gather(*file_tasks, *image_tasks)

        file_uploads: List[FileUpload] = []
        sandbox_files: List[File] = []
        sandbox_images: List[Image] = []

        for result in results:
            if not result:
                continue

            if result[3] == "file":
                file_id, file_path, content, _ = result
                file_uploads.append(FileUpload(path=file_path, content=content))
                sandbox_files.append(File(id=file_id, filepath=file_path))
            elif result[3] == "image":
                image, filepath, content, _ = result
                file_uploads.append(FileUpload(path=filepath, content=content))
                sandbox_images.append(
                    Image(
                        id=image.id,
                        url=image.url,
                        mime_type=image.mime_type,
                        format=image.format,
                    )
                )

        if file_uploads:
            try:
                await sandbox.write_files(file_uploads)
                logger.info(
                    f"Uploaded {len(sandbox_files)} files and {len(sandbox_images)} images to sandbox"
                )
            except Exception as e:
                logger.error(f"Failed to batch upload files to sandbox: {e}")
                return [], images

        return sandbox_files, sandbox_images
