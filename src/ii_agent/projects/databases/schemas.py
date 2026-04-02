from pydantic import BaseModel
from typing import Any, Dict, List


class TableRecordsResult:
    """Result of fetching table records including total count."""

    def __init__(self, rows: List[Dict[str, Any]], total: int):
        self.rows = rows
        self.total = total


class ProjectDatabaseSchemaResponse(BaseModel):
    """List of tables available in the project database."""

    project_id: str
    tables: List[str]


class ProjectDatabaseRecordsResponse(BaseModel):
    """Rows returned from a table query."""

    project_id: str
    table: str
    limit: int
    offset: int
    total: int
    rows: List[Dict[str, Any]]
