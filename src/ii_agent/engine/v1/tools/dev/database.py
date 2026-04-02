from typing import TYPE_CHECKING, Any

from ii_agent.projects.repository import ProjectRepository
from ii_agent.projects.databases.repository import ProjectDatabaseRepository
from ii_agent.projects.databases.models import DatabaseSourceEnum
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.engine.v1.tools.base import BaseAgentTool, ToolResult
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.engine.v1.agents.agent import IIAgent
    from ii_agent.engine.v1.tools.function import FunctionCall

NAME = "get_database_connection"
DISPLAY_NAME = "Get database connection"
DESCRIPTION = """Get a database connection.
- Get connection details for database operations.
- Support multiple database types (currently: postgres).
- Provide connection string for use in applications.
- Requires a project to be initialized first (use fullstack_project_init).
"""
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "database_type": {
            "type": "string",
            "description": "Type of the database to connect to",
            "enum": ["postgres"],
        },
    },
    "required": ["database_type"],
}


class GetDatabaseConnection(BaseAgentTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    def __init__(
        self,
    ) -> None:
        super().__init__()
        self._session_id: str | None = None
        self._user_id: str | None = None

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        await super().on_tool_start(agent, fc)
        self._session_id = getattr(agent, "session_id", None)
        self._user_id = getattr(agent, "user_id", None)

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        try:
            database_type = tool_input["database_type"]
            if not isinstance(database_type, str):
                return ToolResult(
                    llm_content="`database_type` must be a string.",
                    user_display_content="`database_type` must be a string.",
                    is_error=True,
                )

            # Check if session_id is available
            if not self._session_id:
                return ToolResult(
                    llm_content="No session_id available. Cannot create database connection.",
                    user_display_content="No session_id available. Cannot create database connection.",
                    is_error=True,
                )

            session_id = str(self._session_id)

            # Check if a project exists for this session
            _project_repo = ProjectRepository()
            async with get_db_session_local() as db:
                project = await _project_repo.get_by_session_id(db, session_id=session_id)
            if not project:
                return ToolResult(
                    llm_content="No project found for this session. Please initialize a project first using fullstack_project_init tool before requesting a database connection.",
                    user_display_content="No project found for this session. Please initialize a project first using fullstack_project_init tool.",
                    is_error=True,
                )

            user_id = str(self._user_id) if self._user_id else None

            # Check if an active database already exists for this session
            _db_repo = ProjectDatabaseRepository()
            async with get_db_session_local() as db:
                existing_db_record = await _db_repo.get_active_by_session_id(db, session_id=session_id)
            if existing_db_record:
                # Save DATABASE_URL to project secrets
                connection_string = existing_db_record.connection_string
                if user_id and connection_string:
                    await self._save_database_url_to_secrets(
                        session_id=session_id,
                        user_id=user_id,
                        database_url=connection_string,
                    )
                return ToolResult(
                    llm_content=f"Database connection already configured for this session. Connection string: {connection_string}",
                    user_display_content="Database connection already configured for this session.",
                    is_error=False,
                )

            # Pass session_id as database_name
            db_result = await self.dependencies.tool_client.database_connection(database_type, session_id)

            # Store the database connection in the new ProjectDatabase table
            async with get_db_session_local() as db:
                await _db_repo.create(
                    db,
                    session_id=session_id,
                    source=DatabaseSourceEnum.NEONDB.value,
                    connection_string=db_result.get("connection_string", ""),
                    host=db_result.get("host"),
                    database_name=db_result.get("database_name"),
                    role_name=db_result.get("role_name"),
                    branch_name=db_result.get("branch_name"),
                    metadata={
                        "project_id": db_result.get("project_id"),
                        "project_name": db_result.get("project_name"),
                        "is_new_project": db_result.get("is_new_project"),
                        "current_project_count": db_result.get("current_project_count"),
                        "databases_in_project": db_result.get("databases_in_project"),
                        "capacity_remaining": db_result.get("capacity_remaining"),
                        "original_database_name": db_result.get("original_database_name"),
                        "time_taken_ms": db_result.get("time_taken_ms"),
                    },
                )

            # Save DATABASE_URL to project secrets
            connection_string = db_result.get("connection_string")
            if user_id and connection_string:
                await self._save_database_url_to_secrets(
                    session_id=session_id,
                    user_id=user_id,
                    database_url=connection_string,
                )

            return ToolResult(
                llm_content=f"Successfully got database connection. Tool output: {db_result}",
                user_display_content=f"Successfully got database connection. Tool output: {db_result}",
                is_error=False,
            )
        except Exception as exc:
            logger.exception("Failed to get database connection")
            return ToolResult(
                llm_content=f"The database connection request failed: {exc}",
                user_display_content=f"The database connection request failed: {exc}",
                is_error=True,
            )

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
