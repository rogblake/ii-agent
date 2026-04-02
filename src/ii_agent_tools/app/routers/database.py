from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ii_agent_tools.app.app_config import Settings
from ii_agent_tools.app.deps import get_settings_dep, verify_api_key
from ii_agent_tools.integrations.database import create_database_client
from ii_agent_tools.logger import get_logger

router = APIRouter(tags=["database"])
logger = get_logger(__name__)


class BaseRequest(BaseModel):
    pass


class DatabaseConnectionRequest(BaseRequest):
    database_type: str
    database_name: str  # Identifier for the database (e.g., session ID)


class DatabaseConnectionMetadata(BaseModel):
    """Metadata for auditing database connections."""

    host: str
    database_name: str
    original_database_name: str
    role_name: str
    branch_name: str
    project_name: str
    project_id: str
    is_new_project: bool
    current_project_count: int
    databases_in_project: int
    capacity_remaining: int
    created_at: str
    time_taken_ms: int


class DatabaseConnectionResponse(BaseModel):
    success: bool
    connection_string: str | None = None
    metadata: DatabaseConnectionMetadata | None = None
    error: str | None = None
    cost: float | None = None


@router.post("/database", response_model=DatabaseConnectionResponse)
async def database_connection(
    request: DatabaseConnectionRequest,
    auth: dict = Depends(verify_api_key),
    settings: Settings = Depends(get_settings_dep),
):
    """Get a database connection with metadata for auditing."""
    client = None
    try:
        client = create_database_client(request.database_type, settings.database_config)
        result = await client.get_database_connection(request.database_name)
    except ValueError as e:
        logger.error("Invalid database request: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception(
            "Failed to get database connection",
            extra={"database_type": request.database_type, "database_name": request.database_name},
        )
        raise HTTPException(status_code=500, detail="Failed to get database connection")
    finally:
        if client and hasattr(client, "close"):
            await client.close()

    metadata = DatabaseConnectionMetadata(
        host=result["host"],
        database_name=result["database_name"],
        original_database_name=result["original_database_name"],
        role_name=result["role_name"],
        branch_name=result["branch_name"],
        project_name=result["project_name"],
        project_id=result["project_id"],
        is_new_project=result["is_new_project"],
        current_project_count=result["current_project_count"],
        databases_in_project=result["databases_in_project"],
        capacity_remaining=result["capacity_remaining"],
        created_at=result["created_at"],
        time_taken_ms=result["time_taken_ms"],
    )

    return DatabaseConnectionResponse(
        success=True,
        connection_string=result["connection_string"],
        metadata=metadata,
        cost=0,
    )
