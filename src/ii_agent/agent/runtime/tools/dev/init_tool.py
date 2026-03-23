from fastmcp.exceptions import ToolError
from google.genai._interactions.types.image_content import ImageContent
from ii_agent.agent.runtime.tools.base import TextContent
from typing import TYPE_CHECKING, Any

from ii_agent.projects.databases.repository import ProjectDatabaseRepository
from ii_agent.projects.databases.models import DatabaseSourceEnum
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.agent.runtime.tools.mcp.base import MCPTool
from ii_agent.agent.runtime.tools.base import ToolResult
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.agent.runtime.agents.agent import IIAgent
    from ii_agent.agent.runtime.tools.function import FunctionCall

DEFAULT_TIMEOUT = 120

# Name
NAME = "fullstack_project_init"
DISPLAY_NAME = "Initialize application template"

# Description
DESCRIPTION = """Initializes a complete fullstack web application from pre-configured templates with modern development tools and best practices.
## Overview
This tool scaffolds production-ready fullstack applications with automated dependency management, testing infrastructure, and deployment configurations. Choose from optimized templates that include modern UI components, authentication, database integration, and comprehensive testing setups.
## Available Frameworks (default: nextjs-shadcn)
### nextjs-shadcn
Modern TypeScript fullstack with premium UI components
- Frontend: Next.js 14+ (App Router), TypeScript, Tailwind CSS, shadcn/ui components
- Build Tools: Bun package manager, Biome linter/formatter, Jest testing
- Features: Server-side rendering, built-in authentication (NextAuth), Prisma ORM, advanced animations (Framer Motion), real-time features (Socket.io)
- Use Case: Enterprise applications, content management systems, e-commerce platforms
### react-shadcn-python
Fullstack JavaScript + Python with FastAPI backend
- Frontend: React + Vite, JavaScript, Tailwind CSS, shadcn/ui components
- Backend: FastAPI, SQLAlchemy, Pydantic, comprehensive testing suite
- Build Tools: Bun (frontend), pip (backend), automated testing with pytest
- Features: REST API, JWT authentication, database migrations, OpenAPI documentation
- Use Case: API-driven applications, data dashboards, microservices architecture
## Development Guidelines
### Backend Standards
- Testing Requirements: Comprehensive test coverage for all endpoints and business logic
  * Unit tests for all functions and classes
  * Integration tests for API endpoints
  * Edge case and error handling coverage
  * All tests must pass before deployment
- API Design: Follow RESTful principles with OpenAPI documentation
- Security: Input validation, authentication, authorization, SQL injection prevention
### Frontend Standards
- UI/UX: Modern, responsive design using Tailwind CSS utility classes
- Component Architecture: Reusable, composable React components
- State Management: Context API or external libraries as needed
- Performance: Code splitting, lazy loading, optimized builds
- Accessibility: WCAG compliance, semantic HTML, proper ARIA labels
### Deployment Configuration
- Default Ports:
  * Backend: `8080` (auto-increment if unavailable)
  * Frontend: `3000` (auto-increment if unavailable)
- Environment: Development, staging, and production configurations
- Monitoring: Error tracking, performance monitoring, logging
### Debugging Best Practices
- API Testing: Test all endpoints with appropriate HTTP clients
- Error Analysis: Monitor console output and application logs
- Documentation: Consult framework documentation and community resources
- Incremental Development: Test components and features iteratively
## Post-Initialization Steps
1. Navigate to project directory: `cd <project_name>`
2. Install dependencies (automatically handled by tool)
3. Start development servers
4. Review generated documentation and project structure
5. Begin feature development following established patterns
## Quality Assurance
- All templates include pre-configured linting and formatting
- Automated testing infrastructure is ready for immediate use
- Security best practices are implemented by default
- Performance optimizations are built into the build process

Use Database flag to enable database integration.

## Database Source Options
- `default`: Uses NeonDB (managed Postgres). A connection string will be automatically provisioned.
- `supabase`: Uses Supabase as the database backend. Requires Supabase to be connected via integrations.
  When supabase is selected, the agent should use the available Supabase Composio tools
  (SUPABASE_CREATE_A_PROJECT, SUPABASE_BETA_RUN_SQL_QUERY, SUPABASE_GET_PROJECT_API_KEYS, etc.)
  to create the project, set up tables, and retrieve API keys after initialization.
"""
# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "project_name": {
            "type": "string",
            "description": "A name for your project (lowercase, no spaces, use hyphens - if needed). Example: `my-app`, `todo-app`",
        },
        "framework": {
            "type": "string",
            "description": "The framework to use for the project",
            "enum": ["nextjs-shadcn", "react-shadcn-python"],
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
    "required": ["project_name", "framework"],
}


class FullStackInitTool(MCPTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        await super().on_tool_start(agent, fc)
        self._session_id = getattr(agent, "session_id", None)
        self._user_id = getattr(agent, "user_id", None)
        self._host_url = None

        try:
            get_host = getattr(self.sandbox, "get_host", None)
            if callable(get_host):
                self._host_url = await get_host()
            else:
                logger.warning("Host url not supported for this provider")
        except Exception as exc:
            logger.warning("Failed to derive sandbox host_url: %s", exc)

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

                    # Don't pass database_connection to the MCP tool
                    # The agent will use Supabase Composio tools after init
                    tool_input["database"] = False
                    tool_input.pop("database_source", None)

                    result = await self._execute(tool_input)

                    # Append Supabase setup instructions to the result
                    supabase_instructions = (
                        "\n\n## Supabase Database Setup Required\n"
                        "The user chose Supabase as the database provider. You MUST build the entire website/app using Supabase for ALL database operations, authentication, and backend services.\n\n"
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
                        "   - NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co\n"
                        "   - NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon-key>\n"
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

                    return result

                # Default database source: NeonDB provisioning
                # Check if a database already exists for this session
                if session_id:
                    _db_repo = ProjectDatabaseRepository()
                    async with get_db_session_local() as db:
                        existing_db_record = await _db_repo.get_active_by_session_id(
                            db, session_id=session_id
                        )
                    if existing_db_record:
                        # Use existing database connection
                        tool_input["database_connection"] = existing_db_record.connection_string

                    else:
                        # Create new database connection
                        db_connection = await self.dependencies.tool_client.database_connection(
                            "postgres", session_id
                        )
                        tool_input["database_connection"] = db_connection.get("connection_string")

                        # Store in ProjectDatabases table
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
                                    "original_database_name": db_connection.get(
                                        "original_database_name"
                                    ),
                                    "time_taken_ms": db_connection.get("time_taken_ms"),
                                },
                            )

                else:
                    # session_id is required for database operations
                    return ToolResult(
                        llm_content="Cannot initialize database: no session_id available. A session must be created before initializing a project with database.",
                        user_display_content="Cannot initialize database: no session_id available.",
                        is_error=True,
                    )

            # Remove database_source before passing to MCP (not recognized by the internal tool)
            tool_input.pop("database_source", None)
            return await self._execute(tool_input)
        except Exception as e:
            logger.exception("Failed to initialize project")
            return ToolResult(
                llm_content="Failed to initialize project: " + str(e),
                user_display_content="Failed to initialize project: " + str(e),
                is_error=True,
            )

    # TODO: Remove this later when original mcp is deleted, add internal v1 tool for backward compatibility
    async def _execute(self, tool_input: dict[str, Any]) -> ToolResult:
        try:
            remote_input = dict(tool_input)
            if self._host_url and not remote_input.get("host_url"):
                remote_input["host_url"] = self._host_url

            async with self.mcp_client:
                mcp_results = await self.mcp_client.call_tool(
                    self.name,
                    remote_input,
                    timeout=DEFAULT_TIMEOUT,
                )

                llm_content : list[ImageContent | TextContent] = []
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
                # Logic for our internal tools
                if mcp_results.structured_content is not None:
                    user_display_content = mcp_results.structured_content.get(
                        "user_display_content"
                    )
                    is_error = mcp_results.structured_content.get("is_error")
                # For external tools (like MCP) or internal tools that don't have a user_display_content
                if not user_display_content:
                    if not has_image_content:
                        user_display_content = "\n".join([content.text for content in llm_content])
                    else:
                        user_display_content = [content.model_dump() for content in llm_content]

                return ToolResult(
                    llm_content=llm_content,
                    user_display_content=user_display_content,
                    is_error=is_error,
                )
        except ToolError as e:
            return ToolResult(
                llm_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}\n\nPlease analyze the error message to determine if it's due to incorrect input parameters or an internal tool issue. If the error is due to incorrect input, retry with the correct parameters. Otherwise, try an alternative approach and inform the user about the issue.",
                user_display_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                llm_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}\n\nPlease analyze the error message to determine if it's due to incorrect input parameters or an internal tool issue. If the error is due to incorrect input, retry with the correct parameters. Otherwise, try an alternative approach and inform the user about the issue.",
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
        if not isinstance(tool_result, ToolResult):
            return
        if tool_result.is_error:
            return

        raw_result = None
        if isinstance(tool_result.user_display_content, dict):
            raw_result = tool_result.user_display_content
        if not isinstance(raw_result, dict):
            return

        project_name = raw_result.get("project_name")
        if not isinstance(project_name, str):
            return

        framework = raw_result.get("framework")
        framework_str = framework if isinstance(framework, str) else None
        project_dir = raw_result.get("directory") or raw_result.get("project_directory")
        project_dir_str = project_dir if isinstance(project_dir, str) else None
        description = raw_result.get("description")
        description_str = description if isinstance(description, str) else None
        database = raw_result.get("database")
        database_payload = database if isinstance(database, dict) else None

        project_record = await self._persist_project_metadata(
            session_id=str(session_id),
            project_name=project_name,
            framework=framework_str,
            project_path=project_dir_str,
            description=description_str,
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
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Failed to persist project metadata: {exc}")
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
            logger.error(f"Failed to save DATABASE_URL to project secrets: {exc}")
