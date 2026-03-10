"""Handler for publishing a project."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from fastmcp.client.client import CallToolResult

from ii_agent.core.events.models import EventType
from ii_agent.core.events.stream import EventStream
from ii_agent.core.logger import logger
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.agent.sandboxes.e2b import E2BSandboxManager
from ii_agent.realtime.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)
from ii_agent.agent.sandboxes.sandbox_client import MCPClient

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class PublishProjectHandler(CommandHandler):
    """Handler for publishing a project"""

    def __init__(self, event_stream: EventStream, container: ServiceContainer) -> None:
        super().__init__(event_stream=event_stream, container=container)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.PUBLISH_PROJECT

    async def handle(self, content: Dict[str, Any], session_info: SessionInfo) -> None:
        """Handle project deployment to Vercel inside the sandbox."""
        import time

        orch = self.container.deployment_orchestration_service
        session_id = session_info.id

        # Create deployment context (project path, name, records)
        ctx = await orch.create_deployment_context(
            content,
            session_info,
            "vercel",
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

        vercel_api_key = self._extract_api_key(content)
        if not vercel_api_key:
            await self._send_error_event(
                str(session_id),
                message="Vercel API key is required for deployment.",
                error_type="missing_credentials",
            )
            return

        vercel_project_id = ctx.service_name
        shell_session_name = f"deploy-{ctx.session_id_hash}"
        workspace_project_path = f"/workspace/{ctx.project_name}"

        deploy_start = time.time()

        async with get_db_session_local() as db:
            sandbox_record = await self.container.sandbox_service.resolve_sandbox_for_session(
                db, session_info.id, session_service=self.container.session_service
            )

            if sandbox_record and sandbox_record.provider_sandbox_id:
                # Connect to existing sandbox (this wakes it up)
                sandbox_manager = await E2BSandboxManager.connect(
                    sandbox_id=str(sandbox_record.id),
                    session_id=str(sandbox_record.session_id),
                    provider_sandbox_id=sandbox_record.provider_sandbox_id,
                )

                sandbox_url = await sandbox_manager.expose_port(self.container.config.mcp.port)
            else:
                await orch.update_deployment_status(
                    ctx.deployment_id,
                    "failed",
                    deployments_service=self.container.deployments_service,
                    error_message="No sandbox found for session",
                    error_phase="upload",
                    error_details={"code": "SANDBOX_NOT_FOUND"},
                )
                raise ValueError("No sandbox found for session")

        async with MCPClient(sandbox_url) as client:
            await self._ensure_shell_session(
                client,
                shell_session_name,
                ctx.project_path,
            )

            await self._send_event(
                session_id=session_id,
                message=f"Linking {vercel_project_id} with Vercel...",
                event_type=EventType.STATUS_UPDATE,
            )

            # Update status to building
            await orch.update_deployment_status(
                ctx.deployment_id,
                "building",
                deployments_service=self.container.deployments_service,
            )

            link_command = orch.append_success_marker(
                f"cd {orch.shell_quote(workspace_project_path)} && "
                "rm -rf .vercel && "
                f"vercel link --yes --project {orch.shell_quote(vercel_project_id)} --token {orch.shell_quote(vercel_api_key)}"
            )

            try:
                link_output = await self._run_shell_command(
                    client,
                    shell_session_name,
                    link_command,
                    description="Link Vercel project",
                    timeout=179,
                )
            except Exception as exc:  # noqa: BLE001
                await orch.update_deployment_status(
                    ctx.deployment_id,
                    "failed",
                    deployments_service=self.container.deployments_service,
                    error_message=f"Failed to link project with Vercel: {exc}",
                    error_phase="deploy",
                    error_details={
                        "code": "VERCEL_LINK_FAILED",
                        "message": str(exc),
                    },
                )
                await self._send_error_event(
                    str(session_id),
                    message=(f"Failed to link project with Vercel.\nDetails: {exc}"),
                    error_type="deploy_link_failed",
                )
                return

            if not orch.command_succeeded(link_output):
                await orch.update_deployment_status(
                    ctx.deployment_id,
                    "failed",
                    deployments_service=self.container.deployments_service,
                    error_message="Failed to link project with Vercel",
                    error_phase="deploy",
                    error_details={
                        "code": "VERCEL_LINK_FAILED",
                        "output": orch.cleanup_output_for_display(link_output),
                    },
                )
                await self._send_error_event(
                    str(session_id),
                    message=(
                        "Failed to link project with Vercel.\n"
                        f"Output: {orch.cleanup_output_for_display(link_output) or 'No output returned.'}"
                    ),
                    error_type="deploy_link_failed",
                )
                return

            await self._send_event(
                session_id=session_id,
                message="Project linked successfully.",
                event_type=EventType.STATUS_UPDATE,
            )

            await self._send_event(
                session_id=session_id,
                message="Running production deployment...",
                event_type=EventType.STATUS_UPDATE,
            )

            # Update status to deploying
            await orch.update_deployment_status(
                ctx.deployment_id,
                "deploying",
                deployments_service=self.container.deployments_service,
            )

            deploy_command = orch.append_success_marker(
                f"cd {orch.shell_quote(workspace_project_path)} && "
                f"vercel --prod --token {orch.shell_quote(vercel_api_key)} -y"
            )

            try:
                deploy_output = await self._run_shell_command(
                    client,
                    shell_session_name,
                    deploy_command,
                    description="Deploy project to Vercel",
                    timeout=179,
                )
            except Exception as exc:  # noqa: BLE001
                await orch.update_deployment_status(
                    ctx.deployment_id,
                    "failed",
                    deployments_service=self.container.deployments_service,
                    error_message=f"Vercel deployment failed: {exc}",
                    error_phase="deploy",
                    error_details={
                        "code": "VERCEL_DEPLOY_FAILED",
                        "message": str(exc),
                    },
                )
                await self._send_error_event(
                    str(session_id),
                    message=(f"Vercel deployment failed.\nDetails: {exc}"),
                    error_type="deploy_failed",
                )
                return

            if not orch.command_succeeded(deploy_output):
                await orch.update_deployment_status(
                    ctx.deployment_id,
                    "failed",
                    deployments_service=self.container.deployments_service,
                    error_message="Vercel deployment failed",
                    error_phase="deploy",
                    error_details={
                        "code": "VERCEL_DEPLOY_FAILED",
                        "output": orch.cleanup_output_for_display(deploy_output),
                    },
                )
                await self._send_error_event(
                    str(session_id),
                    message=(
                        "Vercel deployment failed.\n"
                        f"Output: {orch.cleanup_output_for_display(deploy_output) or 'No output returned.'}"
                    ),
                    error_type="deploy_failed",
                )
                return

            cleaned_output = orch.cleanup_output(deploy_output)
            deployment_url = orch.extract_deployment_url(cleaned_output, vercel_project_id)

        deploy_duration_ms = int((time.time() - deploy_start) * 1000)

        # Finalize successful deployment
        metadata = {
            "vercel": {
                "project_id": vercel_project_id,
                "deployment_output": orch.cleanup_output_for_display(cleaned_output)[:1000],
            },
        }

        await orch.finalize_successful_deployment(
            ctx,
            deployment_url,
            session_info,
            deployments_service=self.container.deployments_service,
            project_service=self.container.project_service,
            metadata=metadata,
            build_duration_ms=deploy_duration_ms,
        )

        await self._send_event(
            session_id=session_id,
            message=f"Deployment live at {deployment_url}",
            event_type=EventType.SYSTEM,
            deployment_url=deployment_url,
            project_id=vercel_project_id,
            project_name=ctx.project_name,
            deployment={
                "url": deployment_url,
                "project_id": vercel_project_id,
                "project_name": ctx.project_name,
                "provider": "vercel",
                "deployment_id": ctx.deployment_id,
                "version": 1,
            },
        )

    def _extract_api_key(self, content: Dict[str, Any]) -> str | None:
        key = content.get("vercel_api_key")
        if isinstance(key, str) and key.strip():
            return key.strip()

        credentials = content.get("credentials")
        if isinstance(credentials, dict):
            key_candidate = credentials.get("vercel_api_key")
            if isinstance(key_candidate, str) and key_candidate.strip():
                return key_candidate.strip()

        token = content.get("token")
        if isinstance(token, str) and token.strip():
            return token.strip()

        return None

    async def _collect_env_from_files(
        self,
        client: MCPClient,
        session_name: str,
        project_path: str,
    ) -> dict[str, str]:
        orch = self.container.deployment_orchestration_service
        env_vars: dict[str, str] = {}
        base_command = f"cd {orch.shell_quote(project_path)} && "
        for filename in (".env", ".env.local"):
            command = f"{base_command}if [ -f {filename} ]; then cat {filename}; fi"
            command = orch.append_success_marker(command)
            try:
                output = await self._run_shell_command(
                    client,
                    session_name,
                    command,
                    description=f"Read {filename} environment file",
                    timeout=179,
                )
            except Exception:  # noqa: BLE001
                continue
            env_vars.update(self._parse_env_file(orch.cleanup_output(output)))
        return env_vars

    def _parse_env_file(self, content: str) -> dict[str, str]:
        env_vars: dict[str, str] = {}
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            name, value = line.split("=", 1)
            name = name.strip()
            if not name:
                continue
            value = value.strip()
            if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
                value = value[1:-1]
            env_vars[name] = value
        return env_vars

    def _parse_env_payload(self, env_payload: Any) -> dict[str, str]:
        env_vars: dict[str, str] = {}
        if isinstance(env_payload, dict):
            for name, value in env_payload.items():
                if isinstance(name, str) and name:
                    env_vars[name] = "" if value is None else str(value)
        elif isinstance(env_payload, list):
            for item in env_payload:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                value = item.get("value")
                if isinstance(name, str) and name:
                    env_vars[name] = "" if value is None else str(value)
        return env_vars

    def _format_env_flags(self, env_vars: dict[str, str]) -> str:
        orch = self.container.deployment_orchestration_service
        flags: list[str] = []
        for name, value in env_vars.items():
            combined = f"{name}={value}"
            flags.append(f"--env {orch.shell_quote(combined)}")
        return " ".join(flags)

    # ── Transport/MCP concerns (kept in handler) ─────────────────────

    async def _ensure_shell_session(
        self,
        client: MCPClient,
        session_name: str,
        start_directory: str,
    ) -> None:
        tool_name = "BashInit"
        arguments = {
            "session_name": session_name,
        }
        await client.call_tool(tool_name, arguments)

    async def _run_shell_command(
        self,
        client: MCPClient,
        session_name: str,
        command: str,
        *,
        description: str,
        timeout: int = 600,
        wait_for_output: bool = True,
    ) -> str:
        tool_name = "Bash"
        arguments = {
            "session_name": session_name,
            "command": command,
            "description": description,
            "timeout": timeout,
            "wait_for_output": wait_for_output,
        }

        last_error: Exception | None = None
        try:
            result = await client.call_tool(tool_name, arguments)
            return self._extract_tool_output(result)
        except Exception as exc:  # noqa: BLE001
            last_error = exc

        if last_error:
            raise last_error
        return ""

    def _extract_tool_output(self, result: CallToolResult) -> str:
        structured = result.structured_content or {}
        display = structured.get("user_display_content")
        if isinstance(display, str):
            return display
        if isinstance(display, list):
            return "\n".join(str(item) for item in display)

        texts: list[str] = []
        for block in result.content:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                texts.append(text)
        return "\n".join(texts)
