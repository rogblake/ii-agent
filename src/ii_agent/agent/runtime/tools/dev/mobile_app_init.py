"""Mobile app initialization tool for Expo projects."""

from __future__ import annotations

import json
import logging
import shlex
from typing import TYPE_CHECKING, Any

from ii_agent.core.db.manager import get_db_session_local
from ii_agent.agent.runtime.tools.base import TextContent, ToolResult
from ii_agent.agent.runtime.tools.sandbox.base import BaseSandboxTool

if TYPE_CHECKING:
    from ii_agent.agent.runtime.agents.agent import IIAgent
    from ii_agent.agent.runtime.tools.function import FunctionCall

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 180

NAME = "mobile_app_init"
DISPLAY_NAME = "Initialize Mobile App"
DESCRIPTION = """Initializes a React Native mobile application using Expo framework with modern development tooling.

Returns project metadata plus Expo preview/tunnel URLs when available.
"""
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "project_name": {
            "type": "string",
            "description": "Name for the mobile app project (lowercase, no spaces). Example: my-app",
        },
        "template": {
            "type": "string",
            "description": "Expo template to use",
            "enum": ["tabs", "blank", "blank-typescript"],
            "default": "tabs",
        },
        "example": {
            "type": "string",
            "description": "Expo example to use instead of template. Example: `with-reanimated`",
        },
        "with_tailwind": {
            "type": "boolean",
            "description": "Whether to set up NativeWind/Tailwind CSS styling",
            "default": True,
        },
    },
    "required": ["project_name"],
}


class MobileAppInitTool(BaseSandboxTool):
    """Tool for initializing Expo mobile app projects."""

    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        await super().on_tool_start(agent, fc)
        self._session_id = getattr(agent, "session_id", None)

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        try:
            result = await self._run_cli(tool_input)
            await self._apply_web_preview(result)
            return result
        except Exception as e:  # noqa: BLE001
            logger.exception("Failed to initialize mobile app project")
            return ToolResult(
                llm_content="Failed to initialize mobile app project: " + str(e),
                user_display_content="Failed to initialize mobile app project: " + str(e),
                is_error=True,
            )

    async def _run_cli(self, tool_input: dict[str, Any]) -> ToolResult:
        """Build and execute the ii-app mobile init CLI command."""
        project_name = tool_input["project_name"]
        template = tool_input.get("template", "tabs")
        example = tool_input.get("example")
        with_tailwind = tool_input.get("with_tailwind", True)

        cmd_parts = [
            "ii-app",
            "mobile",
            "init",
            project_name,
            "--template",
            template,
            "--workspace",
            "/workspace",
            "--json",
        ]

        if example:
            cmd_parts.extend(["--example", example])
        if not with_tailwind:
            cmd_parts.append("--no-tailwind")

        cmd = " ".join(shlex.quote(p) for p in cmd_parts)
        output = await self.sandbox.run_command(cmd, timeout=DEFAULT_TIMEOUT)
        result = json.loads(output)

        return ToolResult(
            llm_content=[TextContent(type="text", text=output)],
            user_display_content=result,
        )

    async def _apply_web_preview(self, result: ToolResult) -> None:
        """Apply web preview URL to result if sandbox is available."""
        if not result.is_error and isinstance(result.user_display_content, dict):
            web_port = result.user_display_content.get("web_port", 8081)
            try:
                if hasattr(self, "sandbox") and self.sandbox:
                    web_preview_url = await self.sandbox.expose_port(web_port)
                    result.user_display_content["web_preview_url"] = web_preview_url

                    if isinstance(result.llm_content, list) and result.llm_content:
                        first_content = result.llm_content[0]
                        if hasattr(first_content, "text"):
                            updated_text = (
                                first_content.text + f"\n- **Web Preview URL:** `{web_preview_url}`"
                            )
                            result.llm_content[0] = TextContent(
                                type="text",
                                text=updated_text,
                            )
            except Exception as port_error:  # noqa: BLE001
                logger.warning("Failed to expose port {}: {}", web_port, port_error)

    async def on_tool_end(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        if fc.error:
            return

        session_id = getattr(agent, "session_id", None)
        if not session_id:
            return

        tool_result = fc.result
        if not isinstance(tool_result, ToolResult) or tool_result.is_error:
            return

        if not isinstance(tool_result.user_display_content, dict):
            return

        raw_result = tool_result.user_display_content
        project_name = raw_result.get("project_name")
        if not isinstance(project_name, str):
            return

        template = raw_result.get("template")
        template_str = template if isinstance(template, str) else None
        project_dir = (
            raw_result.get("project_path")
            or raw_result.get("project_dir")
            or raw_result.get("project_directory")
        )
        project_dir_str = project_dir if isinstance(project_dir, str) else None

        project_record = await self._persist_project_metadata(
            session_id=str(session_id),
            project_name=project_name,
            framework=f"expo-{template_str}" if template_str else "expo-tabs",
            project_path=project_dir_str,
            description=f"Expo mobile app: {project_name}",
        )

        if project_record:
            raw_result["project"] = project_record
            tool_result.user_display_content = raw_result

    async def _persist_project_metadata(
        self,
        *,
        session_id: str,
        project_name: str,
        framework: str | None,
        project_path: str | None,
        description: str | None,
    ) -> dict | None:
        if not self.dependencies or not self.dependencies.project_service:
            return None

        try:
            async with get_db_session_local() as db:
                project = await self.dependencies.project_service.create_project(
                    db,
                    session_id=session_id,
                    project_name=project_name,
                    framework=framework,
                    project_path=project_path,
                    description=description,
                )
                if project:
                    return {
                        "id": project.id,
                        "name": project.name,
                        "framework": project.framework,
                        "project_path": project.project_path,
                    }
                return None
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to persist mobile app project metadata: {}", exc)
            return None
