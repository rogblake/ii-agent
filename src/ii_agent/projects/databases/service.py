"""Service for introspecting project-linked databases."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, List, Optional
from urllib.parse import urlparse

from sqlalchemy import MetaData, Table, create_engine, func, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


from ii_agent.core.config.settings import Settings
from ii_agent.projects.databases import utils
from ii_agent.projects.databases.exceptions import ProjectDatabaseError
from ii_agent.projects.databases.schemas import ProjectDatabaseResponse, TableRecordsResult
from ii_agent.projects.databases.models import ProjectDatabase
from ii_agent.projects.databases.types import DatabaseSource
from ii_agent.projects.databases.repository import ProjectDatabaseRepository
from ii_agent.projects.repository import ProjectRepository


async def fetch_table_names(connection_url: str) -> List[str]:
    """Return the list of table names available in the target database."""
    return await asyncio.to_thread(_fetch_table_names_sync, connection_url)


async def fetch_table_records(
    connection_url: str,
    *,
    table_name: str,
    limit: int,
    offset: int,
) -> TableRecordsResult:
    """Fetch rows from a specific table along with total count."""
    return await asyncio.to_thread(
        _fetch_table_records_sync, connection_url, table_name, limit, offset
    )


def _fetch_table_names_sync(connection_url: str) -> List[str]:
    engine = create_engine(connection_url, future=True)
    try:
        inspector = inspect(engine)
        return inspector.get_table_names()
    except SQLAlchemyError as exc:  # pragma: no cover - best effort
        raise ProjectDatabaseError(str(exc)) from exc
    finally:
        engine.dispose()


def _fetch_table_records_sync(
    connection_url: str, table_name: str, limit: int, offset: int
) -> TableRecordsResult:
    engine = create_engine(connection_url, future=True)
    try:
        metadata = MetaData()
        try:
            table = Table(table_name, metadata, autoload_with=engine)
        except SQLAlchemyError as exc:  # pragma: no cover - best effort
            raise ProjectDatabaseError(str(exc)) from exc

        stmt = select(table).limit(limit).offset(offset)
        count_stmt = select(func.count()).select_from(table)
        with engine.connect() as conn:
            try:
                result = conn.execute(stmt)
                rows = result.mappings().all()
                total = conn.execute(count_stmt).scalar() or 0
            except SQLAlchemyError as exc:  # pragma: no cover - best effort
                raise ProjectDatabaseError(str(exc)) from exc

        return TableRecordsResult(rows=[dict(row) for row in rows], total=total)
    finally:
        engine.dispose()


class DatabaseService:
    """Service for database introspection operations."""

    def __init__(
        self,
        *,
        project_repo: ProjectRepository,
        db_repo: ProjectDatabaseRepository | None = None,
        config: Settings,
    ) -> None:
        self._config = config
        self._project_repo = project_repo
        self._db_repo = db_repo or ProjectDatabaseRepository()

    @staticmethod
    def _serialize_database_record(db_record: ProjectDatabase) -> dict[str, Any]:
        """Normalize a ProjectDatabase row into the project-facing payload shape."""
        payload: dict[str, Any] = {
            "id": str(db_record.id),
            "session_id": str(db_record.session_id),
            "source": str(db_record.source),
            "connection_string": db_record.connection_string,
            "host": db_record.host,
            "database_name": db_record.database_name,
            "role_name": db_record.role_name,
            "branch_name": db_record.branch_name,
            "is_active": db_record.is_active,
        }
        if isinstance(db_record.db_metadata, dict):
            payload.update(db_record.db_metadata)
        return {key: value for key, value in payload.items() if value is not None}

    async def get_session_db_payload(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
    ) -> Optional[dict[str, Any]]:
        """Return the active ProjectDatabase payload for a session if one exists."""
        db_record = await self._db_repo.get_active_by_session_id(db, session_id)
        if not db_record:
            return None
        return self._serialize_database_record(db_record)

    async def get_project_db_payload(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[dict[str, Any]]:
        """Return the project database payload, preferring ProjectDatabase rows."""
        project = await self._project_repo.get_by_id_and_user(
            db, project_id=project_id, user_id=user_id
        )
        if not project:
            return None

        if project.session_id:
            db_payload = await self.get_session_db_payload(db, project.session_id)
            if db_payload:
                return db_payload

        if isinstance(project.database_json, dict):
            return project.database_json

        return None

    async def get_project_db_connection(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[str]:
        """Fetch the database connection URL for a project."""
        database_payload = await self.get_project_db_payload(
            db, project_id=project_id, user_id=user_id
        )
        return utils.extract_db_url(database_payload)

    async def get_project_db_tables(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[list[str]]:
        """Return the table names for the project's database."""
        connection_url = await self.get_project_db_connection(
            db, project_id=project_id, user_id=user_id
        )
        if not connection_url:
            return None
        return await fetch_table_names(connection_url)

    async def get_project_db_records(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        table_name: str,
        limit: int,
        offset: int,
    ) -> Optional[TableRecordsResult]:
        """Return table records for the project's database."""
        connection_url = await self.get_project_db_connection(
            db, project_id=project_id, user_id=user_id
        )
        if not connection_url:
            return None
        return await fetch_table_records(
            connection_url,
            table_name=table_name,
            limit=limit,
            offset=offset,
        )

    # ------------------------------------------------------------------
    # ProjectDatabase CRUD orchestration
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_connection_string(
        connection_string: str,
    ) -> tuple[str | None, str | None, str | None]:
        """Parse a database connection string to extract host, database_name, and role_name."""
        try:
            parsed = urlparse(connection_string)
            host = parsed.hostname
            database_name = parsed.path.lstrip("/") if parsed.path else None
            role_name = parsed.username
            return host, database_name, role_name
        except Exception:
            return None, None, None

    async def upsert_database_from_url(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        connection_string: str,
        source: str = DatabaseSource.USER,
    ) -> ProjectDatabaseResponse:
        """Upsert a database record from a connection URL.

        If an active database exists for the session, update it.
        Otherwise, create a new one.
        """
        host, database_name, role_name = self._parse_connection_string(connection_string)

        existing = await self._db_repo.get_active_by_session_id(db, session_id)
        if existing:
            existing.source = source
            existing.connection_string = connection_string
            existing.host = host
            existing.database_name = database_name
            existing.role_name = role_name
            entity = await self._db_repo.update(db, existing)
            return ProjectDatabaseResponse.model_validate(entity)

        new_record = ProjectDatabase(
            session_id=session_id,
            source=source,
            connection_string=connection_string,
            host=host,
            database_name=database_name,
            role_name=role_name,
            is_active=True,
        )
        entity = await self._db_repo.save(db, new_record)
        return ProjectDatabaseResponse.model_validate(entity)
