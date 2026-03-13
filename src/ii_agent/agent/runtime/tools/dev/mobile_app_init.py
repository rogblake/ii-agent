"""Mobile app initialization tool for Expo projects."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastmcp.exceptions import ToolError

from ii_agent.core.db.manager import get_db_session_local
from ii_agent.projects.databases.repository import ProjectDatabaseRepository
from ii_agent.projects.databases.models import DatabaseSourceEnum
from ii_agent.agent.runtime.tools.base import ImageContent, TextContent, ToolResult
from ii_agent.agent.runtime.tools.mcp.base import MCPTool

if TYPE_CHECKING:
    from ii_agent.agent.runtime.agents.agent import IIAgent
    from ii_agent.agent.runtime.tools.function import FunctionCall

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 180

NAME = "mobile_app_init"
DISPLAY_NAME = "Initialize Mobile App"
DESCRIPTION = """Initializes a React Native mobile application using Expo framework with modern development tooling.

Returns project metadata plus Expo preview/tunnel URLs when available.

Use Database flag to enable database integration.

## Database Source Options
- `default`: Uses NeonDB (managed Postgres). A connection string will be automatically provisioned.
- `supabase`: Uses Supabase as the database backend. Requires Supabase to be connected via integrations.
  When supabase is selected, the agent should use the available Supabase Composio tools
  (SUPABASE_CREATE_A_PROJECT, SUPABASE_BETA_RUN_SQL_QUERY, SUPABASE_GET_PROJECT_API_KEYS, etc.)
  to create the project, set up tables, and retrieve API keys after initialization.
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
        "database": {
            "type": "boolean",
            "description": "(Optional) whether this project requires a database connection. A postgres connection will be given if True",
            "default": False,
        },
        "database_source": {
            "type": "string",
            "description": "(Optional) The database provider to use. 'default' uses NeonDB (managed Postgres). 'supabase' uses Supabase - requires Supabase integration to be connected. Only relevant when database=true.",
            "enum": ["default", "supabase"],
            "default": "default",
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
        self._session_id = getattr(agent, "session_id", None)
        self._user_id = getattr(agent, "user_id", None)

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        try:
            if tool_input.get("database"):
                session_id = str(self._session_id) if self._session_id else None
                user_id = str(self._user_id) if self._user_id else None
                database_source = tool_input.get("database_source", "default")

                # Supabase database source: skip NeonDB provisioning
                if database_source == "supabase":
                    if not session_id:
                        return ToolResult(
                            llm_content="Cannot initialize database: no session_id available. A session must be created before initializing a project with database.",
                            user_display_content="Cannot initialize database: no session_id available.",
                            is_error=True,
                        )

                    # Record Supabase as the database source (no connection string yet)
                    _db_repo = ProjectDatabaseRepository()
                    async with get_db_session_local() as db:
                        existing_db_record = await _db_repo.get_active_by_session_id(
                            db, session_id=session_id
                        )
                    if not existing_db_record:
                        async with get_db_session_local() as db:
                            await _db_repo.create(
                                db,
                                session_id=session_id,
                                source=DatabaseSourceEnum.SUPABASE.value,
                                connection_string="pending_supabase_setup",
                                metadata={"database_source": "supabase"},
                            )

                    # Don't pass database fields to the MCP tool
                    # The agent will use Supabase Composio tools after init
                    tool_input.pop("database", None)
                    tool_input.pop("database_source", None)

                    result = await self._execute(tool_input)

                    # Append Supabase setup instructions to the result
                    supabase_instructions = (
                        "\n\n## Supabase Database Setup Required\n"
                        "The user chose Supabase as the database provider. You MUST build the entire app using Supabase for ALL database operations, authentication, and backend services.\n\n"
                        "### Step 1: Get organization ID\n"
                        "Call SUPABASE_LIST_ALL_ORGANIZATIONS to get the list of organizations. Extract the `id` from the organization you want to use.\n"
                        "If SUPABASE_LIST_ALL_ORGANIZATIONS is not available, call SUPABASE_LIST_ALL_PROJECTS instead and extract the `organization_id` field from any existing project.\n"
                        "If neither returns an organization ID, ask the user to provide their Supabase organization ID from https://supabase.com/dashboard.\n\n"
                        "### Step 2: Create Supabase project\n"
                        "Call SUPABASE_CREATE_A_PROJECT with ONLY these 4 required parameters:\n"
                        "  - name: \"<project-name>\" (string, required)\n"
                        "  - organization_id: \"<org-id-from-step-1>\" (string, required)\n"
                        "  - region: \"us-east-1\" (string, required)\n"
                        "  - db_pass: \"<strong-password>\" (string, required - generate a strong password with only alphanumeric characters)\n"
                        "DO NOT pass any other parameters (no plan, no template_url, no kps_enabled, no postgres_engine, no release_channel, no desired_instance_size). "
                        "Passing empty strings for optional URL fields will cause validation errors.\n"
                        "IMPORTANT: Save the project 'ref' (project reference ID) from the response - you need it for all subsequent Supabase API calls.\n\n"
                        "### Step 3: Get API keys\n"
                        "Use SUPABASE_GET_PROJECT_API_KEYS with ref=<project-ref> (required) to retrieve the project API keys (anon key, service role key).\n\n"
                        "### Step 4: Configure environment variables\n"
                        "Save the Supabase URL and keys as environment variables in .env:\n"
                        "   - EXPO_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co\n"
                        "   - EXPO_PUBLIC_SUPABASE_ANON_KEY=<anon-key>\n"
                        "   - SUPABASE_SERVICE_ROLE_KEY=<service-role-key> (for server-side operations)\n\n"
                        "### Step 5: Install and set up Supabase client\n"
                        "Install @supabase/supabase-js and create a Supabase client utility (e.g. lib/supabase.ts).\n\n"
                        "### Step 6: Design and create database schema\n"
                        "Use SUPABASE_BETA_RUN_SQL_QUERY with ref=<project-ref> to create all required tables, indexes, and RLS policies. "
                        "Design the schema based on the app requirements.\n\n"
                        "### Step 7: Build with Supabase throughout\n"
                        "Use the Supabase client for ALL data operations: queries, inserts, updates, deletes, real-time subscriptions, and auth. "
                        "Do NOT use direct Postgres connections or any other database. Every data interaction must go through Supabase.\n"
                    )

                    if isinstance(result.llm_content, str):
                        result.llm_content += supabase_instructions
                    elif isinstance(result.llm_content, list):
                        result.llm_content.append(TextContent(type="text", text=supabase_instructions))

                    await self._apply_web_preview(result)
                    return result

                # Default database source: NeonDB provisioning
                if session_id:
                    _db_repo = ProjectDatabaseRepository()
                    async with get_db_session_local() as db:
                        existing_db_record = await _db_repo.get_active_by_session_id(
                            db, session_id=session_id
                        )
                    if existing_db_record:
                        tool_input["database_connection"] = existing_db_record.connection_string
                    else:
                        db_connection = await self.dependencies.tool_client.database_connection(
                            "postgres", session_id
                        )
                        tool_input["database_connection"] = db_connection.get("connection_string")

                        async with get_db_session_local() as db:
                            await _db_repo.create(
                                db,
                                session_id=session_id,
                                source=DatabaseSourceEnum.NEONDB.value,
                                connection_string=db_connection.get("connection_string", ""),
                                host=db_connection.get("host"),
                                database_name=db_connection.get("database_name"),
                                role_name=db_connection.get("role_name"),
                                branch_name=db_connection.get("branch_name"),
                                metadata={
                                    "project_id": db_connection.get("project_id"),
                                    "project_name": db_connection.get("project_name"),
                                    "is_new_project": db_connection.get("is_new_project"),
                                    "current_project_count": db_connection.get("current_project_count"),
                                    "databases_in_project": db_connection.get("databases_in_project"),
                                    "capacity_remaining": db_connection.get("capacity_remaining"),
                                    "original_database_name": db_connection.get("original_database_name"),
                                    "time_taken_ms": db_connection.get("time_taken_ms"),
                                },
                            )
                else:
                    return ToolResult(
                        llm_content="Cannot initialize database: no session_id available. A session must be created before initializing a project with database.",
                        user_display_content="Cannot initialize database: no session_id available.",
                        is_error=True,
                    )

            # Remove fields not recognized by the internal MCP tool
            tool_input.pop("database_source", None)
            tool_input.pop("database", None)
            result = await self._execute(tool_input)
            await self._apply_web_preview(result)
            return result
        except Exception as e:  # noqa: BLE001
            logger.exception("Failed to initialize mobile app project")
            return ToolResult(
                llm_content="Failed to initialize mobile app project: " + str(e),
                user_display_content="Failed to initialize mobile app project: " + str(e),
                is_error=True,
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
        user_id = getattr(agent, "user_id", None)
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
        database = raw_result.get("database")
        database_payload = database if isinstance(database, dict) else None

        project_record = await self._persist_project_metadata(
            session_id=str(session_id),
            project_name=project_name,
            framework=f"expo-{template_str}" if template_str else "expo-tabs",
            project_path=project_dir_str,
            description=f"Expo mobile app: {project_name}",
            database=database_payload,
        )

        if project_record:
            raw_result["project"] = project_record
            tool_result.user_display_content = raw_result

            # Save DATABASE_URL to project secrets after project is created
            if user_id and database_payload:
                database_url = database_payload.get("connection_string")
                if database_url:
                    await self._save_database_url_to_secrets(
                        session_id=str(session_id),
                        user_id=str(user_id),
                        database_url=database_url,
                    )

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

    async def _save_database_url_to_secrets(
        self,
        *,
        session_id: str,
        user_id: str,
        database_url: str,
    ) -> None:
        """Save DATABASE_URL to project secrets (add or overwrite existing secrets)."""
        try:
            async with get_db_session_local() as db:
                project = await self.dependencies.project_service.get_session_project_or_none(
                    db,
                    session_id=session_id,
                    user_id=user_id,
                )
                if not project:
                    return

                # Get existing secrets or empty dict
                existing_secrets = project.secrets_json or {}
                if not isinstance(existing_secrets, dict):
                    existing_secrets = {}

                # Add/overwrite DATABASE_URL
                existing_secrets["DATABASE_URL"] = database_url
                await self.dependencies.project_service.update_session_project_secrets(
                    db,
                    project_id=project.id,
                    secrets=existing_secrets,
                )
            logger.info(f"Saved DATABASE_URL to project secrets for session {session_id}")
        except Exception as exc:
            logger.error("Failed to save DATABASE_URL to project secrets: %s", exc)
