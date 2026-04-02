"""Database introspection endpoints for projects."""

from fastapi import APIRouter, Query

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.projects.exceptions import ProjectNotFoundError
from ii_agent.projects.dependencies import DatabaseServiceDep
from ii_agent.projects.databases.schemas import (
    ProjectDatabaseRecordsResponse,
    ProjectDatabaseSchemaResponse,
)

router = APIRouter(tags=["Project Database"])


@router.get("/{project_id}/database/schema", response_model=ProjectDatabaseSchemaResponse)
async def get_project_database_schema(
    project_id: str,
    current_user: CurrentUser,
    database_service: DatabaseServiceDep,
    db: DBSession,
) -> ProjectDatabaseSchemaResponse:
    """Return the list of tables available in the project's database."""

    tables = await database_service.get_project_db_tables(
        db,
        project_id=project_id,
        user_id=str(current_user.id),
    )

    if tables is None:
        raise ProjectNotFoundError("Project not found or database connection info is missing")

    return ProjectDatabaseSchemaResponse(project_id=project_id, tables=tables)


@router.get(
    "/{project_id}/database/records",
    response_model=ProjectDatabaseRecordsResponse,
)
async def get_project_database_records(
    project_id: str,
    current_user: CurrentUser,
    database_service: DatabaseServiceDep,
    db: DBSession,
    table: str = Query(..., description="Table name to read", min_length=1),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of rows"),
    offset: int = Query(0, ge=0, description="Row offset"),
) -> ProjectDatabaseRecordsResponse:
    """Return rows from a table within the project's database."""

    result = await database_service.get_project_db_records(
        db,
        project_id=project_id,
        user_id=str(current_user.id),
        table_name=table,
        limit=limit,
        offset=offset,
    )

    if result is None:
        raise ProjectNotFoundError("Project not found or database connection info is missing")

    return ProjectDatabaseRecordsResponse(
        project_id=project_id,
        table=table,
        limit=limit,
        offset=offset,
        total=result.total,
        rows=result.rows,
    )
