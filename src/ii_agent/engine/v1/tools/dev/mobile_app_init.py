"""Mobile app initialization tool for Expo projects."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastmcp.exceptions import ToolError

from ii_agent.core.db.manager import get_db_session_local
from ii_agent.engine.v1.tools.base import ImageContent, TextContent, ToolResult
from ii_agent.engine.v1.tools.mcp.base import MCPTool

if TYPE_CHECKING:
    from ii_agent.engine.v1.agents.agent import IIAgent
    from ii_agent.engine.v1.tools.function import FunctionCall

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
        "with_tailwind": {
            "type": "boolean",
            "description": "Whether to set up NativeWind/Tailwind CSS styling",
            "default": False,
            "const": False,
        },
    },
    "required": ["project_name"],
}


class MobileAppInitTool(MCPTool):
    """Tool for initializing Expo mobile app projects."""

    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        await super().on_tool_start(agent, fc)

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        try:
            result = await self._execute(tool_input)

            if not result.is_error and isinstance(result.user_display_content, dict):
                web_port = result.user_display_content.get("web_port", 8081)
                try:
                    if hasattr(self, "sandbox") and self.sandbox:
                        web_preview_url = await self.sandbox.expose_port(web_port)
                        result.user_display_content["web_preview_url"] = web_preview_url

                        if isinstance(result.llm_content, list) and result.llm_content:
                            first_content = result.llm_content[0]
                            if hasattr(first_content, "text"):
                                updated_text = first_content.text.replace(
                                    "use register_deployment tool to get public URL",
                                    f"`{web_preview_url}`",
                                )
                                updated_text = updated_text.replace(
                                    f"Use `register_deployment` tool with port {web_port} to get the web preview URL",
                                    f"Web preview available at: `{web_preview_url}`",
                                )
                                result.llm_content[0] = TextContent(
                                    type="text",
                                    text=updated_text,
                                )
                except Exception as port_error:  # noqa: BLE001
                    logger.warning("Failed to expose port %s: %s", web_port, port_error)

            return result
        except Exception as e:  # noqa: BLE001
            return ToolResult(
                llm_content="Failed to initialize mobile app project: " + str(e),
                user_display_content="Failed to initialize mobile app project: " + str(e),
                is_error=True,
            )

    async def _execute(self, tool_input: dict[str, Any]) -> ToolResult:
        try:
            async with self.mcp_client:
                mcp_results = await self.mcp_client.call_tool(
                    self.name + "_internal",
                    tool_input,
                    timeout=DEFAULT_TIMEOUT,
                )

                llm_content: list[TextContent | ImageContent] = []
                has_image_content = False
                for mcp_result in mcp_results.content:
                    if mcp_result.type == "text":
                        llm_content.append(TextContent(type="text", text=mcp_result.text))
                    elif mcp_result.type == "image":
                        llm_content.append(
                            ImageContent(
                                type="image",
                                data=mcp_result.data,
                                mime_type=mcp_result.mimeType,
                            )
                        )
                        has_image_content = True
                    else:
                        raise ValueError(f"Unknown result type: {mcp_result.type}")

                user_display_content = None
                is_error = False
                if mcp_results.structured_content is not None:
                    user_display_content = mcp_results.structured_content.get(
                        "user_display_content"
                    )
                    is_error = mcp_results.structured_content.get("is_error")

                if not user_display_content:
                    if not has_image_content:
                        user_display_content = "\n".join(
                            [content.text for content in llm_content if hasattr(content, "text")]
                        )
                    else:
                        user_display_content = [
                            content.model_dump() for content in llm_content
                        ]

                return ToolResult(
                    llm_content=llm_content,
                    user_display_content=user_display_content,
                    is_error=is_error,
                )
        except ToolError as e:
            return ToolResult(
                llm_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}",
                user_display_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}",
                is_error=True,
            )
        except Exception as e:  # noqa: BLE001
            return ToolResult(
                llm_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}",
                user_display_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}",
                is_error=True,
            )

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
        project_dir = raw_result.get("project_path") or raw_result.get("project_directory")
        project_dir_str = project_dir if isinstance(project_dir, str) else None

        project_record = await self._persist_project_metadata(
            session_id=str(session_id),
            project_name=project_name,
            framework=f"expo-{template_str}" if template_str else "expo-tabs",
            project_path=project_dir_str,
            description=f"Expo mobile app: {project_name}",
            database=None,
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
        database: dict | None,
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
                    database=database,
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
            logger.error("Failed to persist mobile app project metadata: %s", exc)
            return None
