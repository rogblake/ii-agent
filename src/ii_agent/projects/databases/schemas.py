from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ii_agent.projects.databases.types import DatabaseSource


class ProjectDatabaseResponse(BaseModel):
    """Pydantic response model for a project database record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    source: DatabaseSource
    connection_string: str
    host: Optional[str] = None
    database_name: Optional[str] = None
    role_name: Optional[str] = None
    branch_name: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TableRecordsResult:
    """Result of fetching table records including total count."""

    def __init__(self, rows: List[Dict[str, Any]], total: int):
        self.rows = rows
        self.total = total


class ProjectDatabaseSchemaResponse(BaseModel):
    """List of tables available in the project database."""

    project_id: UUID
    tables: List[str]


class ProjectDatabaseRecordsResponse(BaseModel):
    """Rows returned from a table query."""

    project_id: UUID
    table: str
    limit: int
    offset: int
    total: int
    rows: List[Dict[str, Any]]
