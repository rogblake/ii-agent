"""Handler for publishing a project to Google Cloud Run."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from ii_agent.agent.events.models import EventType
from ii_agent.agent.events.stream import EventStream
from ii_agent.core.logger import logger
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.projects.cloud_run.schemas import CloudRunConfig, DeploymentResult, DeploymentStatus
from ii_agent.projects.cloud_run.service import CloudRunPublisher
from ii_agent.agent.sandboxes.base import SandboxManager
from ii_agent.agent.sandboxes.e2b import E2BSandboxManager
from ii_agent.agent.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class CloudRunPublishHandler(CommandHandler):
    """Handler for publishing a project to Cloud Run."""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)
        self._publisher: CloudRunPublisher | None = None

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.PUBLISH_CLOUD_RUN

    @property
    def publisher(self) -> CloudRunPublisher:
        """Lazy-loaded Cloud Run publisher."""
        if self._publisher is None:
            config = CloudRunConfig.from_env()
            self._publisher = CloudRunPublisher(
                config=config,
                on_status_update=None,
            )
        return self._publisher

    async def handle(self, content: Dict[str, Any], session_info: SessionInfo) -> None:
        """Handle project deployment to Cloud Run."""
        import time

        orch = self.container.deployment_orchestration_service
        session_id = session_info.id

        try:
            # Create deployment context (project path, name, records)
            ctx = await orch.create_deployment_context(
                content,
                session_info,
                "cloud_run",
                project_service=self.container.project_service,
                deployments_service=self.container.deployments_service,
            )
            if not ctx:
                await self._send_error_event(
                    str(session_id),
                    message="Project path is required to publish the project.",
                    error_type="missing_project_path",
                )
                return

            # Get sandbox for the session
            await self._send_event(
                session_id=session_id,
                message="Connecting to sandbox...",
                event_type=EventType.STATUS_UPDATE,
            )

            sandbox = await self._get_sandbox(session_info)
            if not sandbox:
                await orch.update_deployment_status(
                    ctx.deployment_id,
                    "failed",
                    deployments_service=self.container.deployments_service,
                    error_message="Failed to connect to sandbox.",
                    error_phase="upload",
                    error_details={"code": "SANDBOX_CONNECTION_FAILED"},
                )
                await self._send_error_event(
                    str(session_id),
                    message="Failed to connect to sandbox.",
                    error_type="sandbox_connection_failed",
                )
                return

            # Download source from sandbox
            await self._send_event(
                session_id=session_id,
                message="Downloading source code from sandbox...",
                event_type=EventType.STATUS_UPDATE,
            )

            upload_start = time.time()
            source_bytes = await self._download_source_from_sandbox(
                sandbox, ctx.project_path, ctx.project_name
            )
            if not source_bytes:
                await orch.update_deployment_status(
                    ctx.deployment_id,
                    "failed",
                    deployments_service=self.container.deployments_service,
                    error_message="Failed to download source code from sandbox.",
                    error_phase="upload",
                    error_details={"code": "SOURCE_DOWNLOAD_FAILED"},
                )
                await self._send_error_event(
                    str(session_id),
                    message="Failed to download source code from sandbox.",
                    error_type="source_download_failed",
                )
                return

            # Extract environment variables if provided
            env_vars = self._extract_env_vars(content)

            # Deploy to Cloud Run
            await self._send_event(
                session_id=session_id,
                message="Uploading source code...",
                event_type=EventType.STATUS_UPDATE,
            )

            # Update deployment status to building
            await orch.update_deployment_status(
                ctx.deployment_id,
                "building",
                deployments_service=self.container.deployments_service,
            )

            # Create status callback
            async def on_status(status: DeploymentStatus, message: str):
                await self._send_event(
                    session_id=session_id,
                    message=message,
                    event_type=EventType.STATUS_UPDATE,
                )

            # Set up status callback (synchronous wrapper)
            def status_callback(status: DeploymentStatus, message: str):
                import asyncio

                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(on_status(status, message))
                    else:
                        loop.run_until_complete(on_status(status, message))
                except Exception:
                    pass  # Best effort status updates

            self.publisher.on_status_update = status_callback

            # Execute deployment
            result = await self.publisher.publish(
                source_bytes=source_bytes,
                service_name=ctx.service_name,
                env_vars=env_vars,
            )

            upload_duration_ms = int((time.time() - upload_start) * 1000)

            # Always persist available metadata regardless of success/failure
            if ctx.deployment_id:
                metadata = self._build_metadata(ctx.service_name, result)
                async with get_db_session_local() as db:
                    await self.container.deployments_service.update_deployment_metadata(
                        db,
                        deployment_id=ctx.deployment_id,
                        metadata=metadata,
                        upload_duration_ms=upload_duration_ms,
                        build_duration_ms=result.build_duration_ms,
                    )
                    await db.commit()

            if not result.success:
                # Update deployment with failure details
                error_phase = "deploy"
                if result.error and "build" in result.error.lower():
                    error_phase = "build"
                elif result.error and "push" in result.error.lower():
                    error_phase = "push"

                await orch.update_deployment_status(
                    ctx.deployment_id,
                    "failed",
                    deployments_service=self.container.deployments_service,
                    error_message=result.error,
                    error_phase=error_phase,
                    error_details={
                        "code": "DEPLOYMENT_FAILED",
                        "message": result.error,
                    },
                )

                await self._send_error_event(
                    str(session_id),
                    message=f"Deployment failed: {result.error}",
                    error_type="deploy_failed",
                )
                return

            deployment_url = result.url

            # Finalize successful deployment
            await orch.finalize_successful_deployment(
                ctx,
                deployment_url,
                session_info,
                deployments_service=self.container.deployments_service,
                project_service=self.container.project_service,
            )

            # Send success event
            await self._send_event(
                session_id=session_id,
                message=f"Deployment live at {deployment_url}",
                event_type=EventType.SYSTEM,
                deployment_url=deployment_url,
                project_id=ctx.service_name,
                project_name=ctx.project_name,
                deployment={
                    "url": deployment_url,
                    "cloud_run_url": deployment_url,
                    "project_id": ctx.service_name,
                    "project_name": ctx.project_name,
                    "provider": "cloud_run",
                    "deployment_id": ctx.deployment_id,
                    "version": 1,
                },
            )

        except Exception as exc:
            logger.exception("Failed to deploy to Cloud Run")
            # Update deployment with failure and persist available metadata
            if ctx and ctx.deployment_id:
                try:
                    metadata = self._build_metadata(ctx.service_name, result=None)
                    async with get_db_session_local() as db:
                        await self.container.deployments_service.update_deployment_metadata(
                            db,
                            deployment_id=ctx.deployment_id,
                            metadata=metadata,
                        )
                        await db.commit()
                except Exception:
                    pass  # Best effort metadata save

                await orch.update_deployment_status(
                    ctx.deployment_id,
                    "failed",
                    deployments_service=self.container.deployments_service,
                    error_message=str(exc),
                    error_phase="deploy",
                    error_details={
                        "code": "UNEXPECTED_ERROR",
                        "message": str(exc),
                    },
                )
            await self._send_error_event(
                str(session_id),
                message=f"Deployment failed: {str(exc)}",
                error_type="deploy_failed",
            )

    # ── Sandbox I/O (kept in handler) ────────────────────────────────

    async def _get_sandbox(self, session_info: SessionInfo) -> SandboxManager | None:
        """Get sandbox instance for the session using resolve_sandbox_for_session."""
        try:
            async with get_db_session_local() as db:
                sandbox_record = await self.container.sandbox_service.resolve_sandbox_for_session(
                    db, session_info.id, session_service=self.container.session_service
                )

                if sandbox_record and sandbox_record.provider_sandbox_id:
                    sandbox = await E2BSandboxManager.connect(
                        sandbox_id=str(sandbox_record.id),
                        session_id=str(sandbox_record.session_id),
                        provider_sandbox_id=sandbox_record.provider_sandbox_id,
                    )
                    return sandbox
                else:
                    return None

        except Exception:
            logger.exception("Failed to get sandbox for session %s", session_info.id)
            return None

    async def _download_source_from_sandbox(
        self,
        sandbox: SandboxManager,
        project_path: str,
        project_name: str,
    ) -> bytes | None:
        """Download source code from sandbox as a tar.gz archive."""
        try:
            # Normalize the project path
            if not project_path.startswith("/"):
                project_path = f"/workspace/{project_path}"

            # Create a tar.gz of the source directory, excluding node_modules etc.
            tar_path = f"/tmp/{project_name}-source.tar.gz"

            # Build exclusion patterns
            excludes = [
                "node_modules",
                ".git",
                ".next",
                "__pycache__",
                ".venv",
                "venv",
                "dist",
                "build",
                ".cache",
                "coverage",
                ".nyc_output",
                "*.pyc",
                ".DS_Store",
            ]
            exclude_args = " ".join(f"--exclude='{e}'" for e in excludes)

            # Create tar archive in sandbox
            tar_command = f"cd {project_path} && tar {exclude_args} -czf {tar_path} ."
            await sandbox.run_command(tar_command)

            # Download the tar file
            tar_content = await sandbox.download_file(tar_path, format="bytes")

            # Cleanup tar file in sandbox
            await sandbox.run_command(f"rm -f {tar_path}")

            if isinstance(tar_content, bytes):
                return tar_content
            elif hasattr(tar_content, "__aiter__"):
                chunks = []
                async for chunk in tar_content:
                    chunks.append(chunk)
                return b"".join(chunks)
            else:
                logger.error(f"Unexpected tar content type: {type(tar_content)}")
                return None

        except Exception:
            logger.exception("Failed to download source from sandbox")
            return None

    # ── Cloud Run specific helpers (kept in handler) ─────────────────

    def _build_metadata(
        self,
        service_name: str,
        result: DeploymentResult | None = None,
    ) -> Dict[str, Any]:
        """Build deployment metadata from available data."""
        config = self.publisher.config

        metadata: Dict[str, Any] = {
            "config": {
                "memory": config.memory if config else None,
                "cpu": config.cpu if config else None,
                "min_instances": config.min_instances if config else None,
                "max_instances": config.max_instances if config else None,
            },
            "cloud_run": {
                "service_name": service_name,
                "region": config.region if config else None,
                "project_id": config.project_id if config else None,
            },
        }

        if result:
            if result.source_bucket or result.source_object:
                metadata["source"] = {
                    "bucket": result.source_bucket,
                    "object": result.source_object,
                }
            if result.image_url or result.image_digest:
                metadata["image"] = {
                    "url": result.image_url,
                    "digest": result.image_digest,
                }
            if result.build_id:
                metadata["cloud_run"]["build_id"] = result.build_id

        return metadata

    def _extract_env_vars(self, content: Dict[str, Any]) -> dict[str, str] | None:
        env_vars: dict[str, str] = {}

        if isinstance(content.get("env_vars"), dict):
            for key, value in content["env_vars"].items():
                if isinstance(key, str) and key:
                    env_vars[key] = str(value) if value is not None else ""

        credentials = content.get("credentials")
        if isinstance(credentials, dict):
            env = credentials.get("environment")
            if isinstance(env, dict):
                for key, value in env.items():
                    if isinstance(key, str) and key:
                        env_vars[key] = str(value) if value is not None else ""

        return env_vars if env_vars else None
