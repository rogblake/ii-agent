"""Service for deployment orchestration logic shared between publish handlers.

Extracts project resolution, deployment record management, and utility
methods that were duplicated across ``PublishProjectHandler`` (Vercel) and
``CloudRunPublishHandler``.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import uuid
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ii_agent.core.config.settings import Settings
from ii_agent.core.db.manager import get_db_session_local

if TYPE_CHECKING:
    from ii_agent.projects.deployments.service import DeploymentsService
    from ii_agent.projects.service import ProjectService
    from ii_agent.sessions.schemas import SessionInfo

logger = logging.getLogger(__name__)


_SUCCESS_MARKER = "__II_PUBLISH_SUCCESS__"


@dataclass
class DeploymentContext:
    """Context gathered during deployment setup."""

    project_path: str
    project_name: str
    service_name: str
    session_id_hash: str
    db_project_id: str | None
    deployment_id: str | None


class DeploymentOrchestrationService:
    """Shared deployment logic for Vercel and Cloud Run handlers."""

    def __init__(self, *, config: Settings) -> None:
        self._config = config

    # ── Project resolution ───────────────────────────────────────────

    @staticmethod
    def resolve_project_path(
        project_path: str | None, session_info: SessionInfo
    ) -> str | None:
        """Normalize a project path relative to the session workspace."""
        if isinstance(project_path, str) and project_path.strip():
            project_path = project_path.strip()
        else:
            project_path = session_info.workspace_dir

        if not isinstance(project_path, str) or not project_path:
            return None

        if project_path.startswith("./"):
            project_path = project_path[2:]

        if not os.path.isabs(project_path):
            project_path = os.path.join(session_info.workspace_dir, project_path)

        return project_path.rstrip()

    @staticmethod
    def resolve_project_name(
        provided_name: Any, project_path: str, *, cloud_run: bool = False
    ) -> str:
        """Sanitize a project name, handling Cloud Run constraints when needed."""
        if isinstance(provided_name, str) and provided_name.strip():
            candidate = provided_name.strip()
        else:
            candidate = os.path.basename(project_path.rstrip(os.sep)) or "project"

        sanitized = re.sub(r"[^a-zA-Z0-9-]+", "-", candidate)
        sanitized = sanitized.strip("-").lower()

        if cloud_run:
            # Cloud Run requires alpha prefix and max 50 chars
            if sanitized and not sanitized[0].isalpha():
                sanitized = "app-" + sanitized
            return sanitized[:50] or "project"

        return sanitized or "project"

    @staticmethod
    def generate_service_name(
        project_name: str,
        session_id: uuid.UUID | str,
        *,
        prefix: str = "",
        suffix: str = "",
    ) -> tuple[str, str]:
        """Generate a service name and session-ID hash.

        Returns ``(service_name, session_id_hash)``.
        """
        session_id_hash = hashlib.sha256(str(session_id).encode()).hexdigest()[:8]
        parts = [p for p in (prefix, project_name, suffix, session_id_hash) if p]
        service_name = "-".join(parts)
        return service_name, session_id_hash

    # ── Deployment context creation ──────────────────────────────────

    async def create_deployment_context(
        self,
        content: dict[str, Any],
        session_info: SessionInfo,
        provider: str,
        *,
        project_service: ProjectService,
        deployments_service: DeploymentsService,
    ) -> DeploymentContext | None:
        """Create project record + deployment record from handler content.

        Returns a :class:`DeploymentContext` on success, or ``None`` if the
        project_path cannot be resolved.
        """
        cloud_run = provider == "cloud_run"
        project_path = self.resolve_project_path(
            content.get("project_path"), session_info
        )
        if not project_path:
            return None

        project_name = self.resolve_project_name(
            content.get("project_name"), project_path, cloud_run=cloud_run
        )

        if cloud_run:
            service_name, session_id_hash = self.generate_service_name(
                project_name, session_info.id
            )
        else:
            session_id_hash = hashlib.sha256(
                str(session_info.id).encode()
            ).hexdigest()[:8]
            service_name = f"{project_name}-ii-{session_id_hash}"

        db_project_id: str | None = None
        deployment_id: str | None = None

        try:
            async with get_db_session_local() as db:
                project = await project_service.get_session_project_or_none(
                    db,
                    session_id=str(session_info.id),
                    user_id=session_info.user_id,
                )
                db_project_id = project.id if project else None

                if db_project_id:
                    deployment_record = (
                        await deployments_service.create_deployment(
                            db,
                            project_id=db_project_id,
                            user_id=session_info.user_id,
                            provider=provider,
                            environment="production",
                            source_path=project_path,
                            snapshot_id=content.get("revision"),
                        )
                    )
                    deployment_id = deployment_record.id
                    logger.info(
                        "Created %s deployment record %s for project %s (v%s)",
                        provider,
                        deployment_id,
                        db_project_id,
                        deployment_record.version,
                    )
                await db.commit()
        except Exception as exc:
            logger.warning("Failed to create deployment record: %s", exc)

        return DeploymentContext(
            project_path=project_path,
            project_name=project_name,
            service_name=service_name,
            session_id_hash=session_id_hash,
            db_project_id=db_project_id,
            deployment_id=deployment_id,
        )

    # ── Deployment status updates ────────────────────────────────────

    async def update_deployment_status(
        self,
        deployment_id: str | None,
        status: str,
        *,
        deployments_service: DeploymentsService,
        error_message: str | None = None,
        error_phase: str | None = None,
        error_details: dict | None = None,
        deployment_url: str | None = None,
    ) -> None:
        """Update deployment status if ``deployment_id`` is not None."""
        if not deployment_id:
            return
        async with get_db_session_local() as db:
            await deployments_service.update_deployment_status(
                db,
                deployment_id=deployment_id,
                status=status,
                error_message=error_message,
                error_phase=error_phase,
                error_details=error_details,
                deployment_url=deployment_url,
            )
            await db.commit()

    async def finalize_successful_deployment(
        self,
        deployment_context: DeploymentContext,
        deployment_url: str,
        session_info: SessionInfo,
        *,
        deployments_service: DeploymentsService,
        project_service: ProjectService,
        metadata: dict | None = None,
        build_duration_ms: int | None = None,
    ) -> None:
        """Consolidate the success path for both handlers."""
        deployment_id = deployment_context.deployment_id
        db_project_id = deployment_context.db_project_id

        if deployment_id:
            async with get_db_session_local() as db:
                await deployments_service.update_deployment_status(
                    db,
                    deployment_id=deployment_id,
                    status="deployed",
                    deployment_url=deployment_url,
                )
                if metadata:
                    await deployments_service.update_deployment_metadata(
                        db,
                        deployment_id=deployment_id,
                        metadata=metadata,
                        build_duration_ms=build_duration_ms,
                    )
                if db_project_id:
                    await deployments_service.set_active_deployment(
                        db,
                        project_id=db_project_id,
                        deployment_id=deployment_id,
                    )
                await db.commit()

        try:
            async with get_db_session_local() as db:
                await project_service.update_session_project_production_url(
                    db,
                    session_id=str(session_info.id),
                    user_id=session_info.user_id,
                    production_url=deployment_url,
                )
                await db.commit()
        except Exception as exc:
            logger.warning(
                "Failed to persist deployment URL for session %s: %s",
                session_info.id,
                exc,
            )

    # ── Static utility methods ───────────────────────────────────────

    @staticmethod
    def shell_quote(value: str) -> str:
        """Shell-safe quoting."""
        return shlex.quote(value)

    @staticmethod
    def append_success_marker(command: str) -> str:
        """Append a success marker to a shell command."""
        return f"{command} && echo {_SUCCESS_MARKER}"

    @staticmethod
    def command_succeeded(output: str) -> bool:
        """Check whether a command produced the success marker."""
        return bool(output and _SUCCESS_MARKER in output)

    @staticmethod
    def cleanup_output(output: str) -> str:
        """Strip the success marker from command output."""
        if not output:
            return ""
        return output.replace(_SUCCESS_MARKER, "").strip()

    @staticmethod
    def redact_secrets(output: str) -> str:
        """Redact sensitive tokens from output."""
        if not output:
            return ""
        output = re.sub(r"(--token\s+)(\S+)", r"\1[REDACTED]", output)
        output = re.sub(r"(--token=)(\S+)", r"\1[REDACTED]", output)
        output = re.sub(
            r"(VERCEL_(?:ACCESS_)?TOKEN=)(\S+)", r"\1[REDACTED]", output
        )
        return output

    @classmethod
    def cleanup_output_for_display(cls, output: str) -> str:
        """Clean up and redact output for user display."""
        return cls.redact_secrets(cls.cleanup_output(output))

    @staticmethod
    def extract_deployment_url(output: str, project_id: str) -> str:
        """Extract a deployment URL from Vercel output."""
        if output:
            production_match = re.search(
                r"Production:\s*(https://[^\s\]]+)", output, re.IGNORECASE
            )
            if production_match:
                return production_match.group(1)
            vercel_match = re.search(
                r"https://[^\s\]]+vercel\.app", output, re.IGNORECASE
            )
            if vercel_match:
                return vercel_match.group(0)
            generic_match = re.search(r"https://[^\s\]]+", output)
            if generic_match:
                return generic_match.group(0)
        return f"https://{project_id}.vercel.app"


__all__ = ["DeploymentOrchestrationService", "DeploymentContext"]
