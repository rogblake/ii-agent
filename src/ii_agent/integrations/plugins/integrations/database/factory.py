import asyncio
import os
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator, TypedDict
from urllib.parse import quote_plus

import aiohttp

from ii_agent_tools.logger import get_logger
from ii_agent_tools.integrations.database.config import DatabaseConfig

NEON_DB_KEY_ERROR_MSG = "PLEASE SET NEONDB KEY.... ask user to redeploy ii-agent with neondb key for this tool to work, or for now please use sqlite"

# NeonDB limits and constants
MAX_DATABASES_PER_BRANCH = 500
MAX_PROJECTS = 100
NEON_API_BASE = "https://console.neon.tech/api/v2"
PROJECT_PREFIX = "project_"

# Retry settings for operations that may conflict with background tasks
MAX_RETRIES = 10
RETRY_DELAY_SECONDS = 2

logger = get_logger(__name__)


class NeonDBError(Exception):
    """Base exception for NeonDB operations."""
    pass


class NeonDBCapacityError(NeonDBError):
    """Raised when NeonDB capacity limits are reached."""
    pass


class NeonDBConflictError(NeonDBError):
    """Raised when there's a conflict with ongoing operations."""
    pass


class NeonDBResourceExistsError(NeonDBError):
    """Raised when a resource already exists."""
    pass


class DatabaseConnections(TypedDict):
    """Connection strings for dev and prod environments."""
    dev: str
    prod: str


class DatabaseConnectionResult(TypedDict):
    """Result of database connection creation with metadata for auditing."""
    # Connection details
    connection_string: str
    host: str

    # Database info
    database_name: str  # Sanitized name
    original_database_name: str  # Original name before sanitization
    role_name: str
    branch_name: str

    # Project info
    project_name: str
    project_id: str
    is_new_project: bool  # Whether a new project was created

    # Capacity info
    current_project_count: int  # Total number of managed projects
    databases_in_project: int  # Number of databases in this project's main branch
    capacity_remaining: int  # How many more databases can fit in this project

    # Timing
    created_at: str  # ISO format timestamp
    time_taken_ms: int  # Time taken to create the database in milliseconds


class DatabaseClient(ABC):
    @abstractmethod
    async def get_database_connection(self, database_name: str) -> DatabaseConnectionResult:
        pass


class PostgresDatabaseClient(DatabaseClient):
    """
    PostgreSQL database client using NeonDB.

    Structure:
    - Projects: project_0, project_1, ... (created as needed, max 100)
    - Each project has 2 branches: main (prod) and dev
    - Each branch can have up to 500 databases
    - Each database has its own role for isolation

    Usage:
        async with PostgresDatabaseClient(config) as client:
            result = await client.get_database_connection("my_db")
    """

    # Class-level lock for database creation to prevent race conditions
    _creation_lock: asyncio.Lock | None = None

    def __init__(self, setting: DatabaseConfig):
        self.setting = setting
        self.neon_db_api_key = setting.neon_db_api_key
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "PostgresDatabaseClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - ensures session is closed."""
        await self.close()

    @classmethod
    def _get_creation_lock(cls) -> asyncio.Lock:
        """Get or create the class-level creation lock."""
        if cls._creation_lock is None:
            cls._creation_lock = asyncio.Lock()
        return cls._creation_lock

    @asynccontextmanager
    async def _get_session(self) -> AsyncIterator[aiohttp.ClientSession]:
        """Get or create a reusable aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        try:
            yield self._session
        except Exception:
            # On error, close session so next call creates a fresh one
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = None
            raise

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _get_headers(self) -> dict[str, str]:
        """Get headers for NeonDB API requests."""
        if not self.neon_db_api_key:
            raise ValueError(NEON_DB_KEY_ERROR_MSG)
        return {
            "Authorization": f"Bearer {self.neon_db_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _api_request(
        self,
        method: str,
        endpoint: str,
        json: dict | None = None,
        expected_status: list[int] | None = None,
        retry_on_conflict: bool = True,
    ) -> dict:
        """Make an API request to NeonDB with retry logic for conflicting operations."""
        if expected_status is None:
            expected_status = [200, 201]

        url = f"{NEON_API_BASE}{endpoint}"

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                async with self._get_session() as session:
                    async with session.request(
                        method, url, headers=self._get_headers(), json=json
                    ) as response:
                        if response.status in expected_status:
                            return await response.json()

                        text = await response.text()

                        # Handle conflict (423) - retry
                        if response.status == 423 and retry_on_conflict:
                            logger.info(
                                f"NeonDB conflict (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {RETRY_DELAY_SECONDS}s..."
                            )
                            last_error = NeonDBConflictError(
                                f"NeonDB API conflict: {method} {endpoint} - {text}"
                            )
                            await asyncio.sleep(RETRY_DELAY_SECONDS)
                            continue

                        # Handle resource already exists (409)
                        if response.status == 409:
                            raise NeonDBResourceExistsError(
                                f"Resource already exists: {method} {endpoint} - {text}"
                            )

                        # Handle other errors
                        raise NeonDBError(
                            f"NeonDB API error: {method} {endpoint} - {response.status} - {text}"
                        )
            except aiohttp.ClientError as e:
                raise NeonDBError(f"Network error calling NeonDB API: {str(e)}") from e

        # If we exhausted all retries
        raise last_error or NeonDBConflictError("NeonDB API request failed after retries")

    # -------------------------------------------------------------------------
    # Project Management
    # -------------------------------------------------------------------------

    async def get_all_projects(self) -> list[dict]:
        """Get all NeonDB projects."""
        data = await self._api_request("GET", "/projects?limit=200")
        return data.get("projects", [])

    async def _get_managed_projects(self) -> list[dict]:
        """Get projects managed by this system (project_0, project_1, ...)."""
        projects = await self.get_all_projects()
        managed = []
        for p in projects:
            name = p.get("name", "")
            if name.startswith(PROJECT_PREFIX):
                try:
                    # Extract index from project_N
                    index = int(name[len(PROJECT_PREFIX):])
                    p["_index"] = index
                    managed.append(p)
                except ValueError:
                    continue
        # Sort by index
        managed.sort(key=lambda x: x["_index"])
        return managed

    async def _create_project(self, index: int) -> dict:
        """Create a new NeonDB project with the given index."""
        payload = {
            "project": {
                "name": f"{PROJECT_PREFIX}{index}",
                "pg_version": 17,
            }
        }
        data = await self._api_request("POST", "/projects", json=payload)
        logger.info(f"Created NeonDB project: {PROJECT_PREFIX}{index}")
        return data["project"]

    async def delete_project(self, project_id: str) -> bool:
        """Delete a NeonDB project."""
        await self._api_request("DELETE", f"/projects/{project_id}", expected_status=[200, 204])
        logger.info(f"Deleted NeonDB project: {project_id}")
        return True

    # -------------------------------------------------------------------------
    # Branch Management
    # -------------------------------------------------------------------------

    async def _get_branches(self, project_id: str) -> list[dict]:
        """Get all branches for a project."""
        data = await self._api_request("GET", f"/projects/{project_id}/branches")
        return data.get("branches", [])

    async def _get_main_branch(self, project_id: str, branches: list[dict] | None = None) -> dict:
        """Get the main (default) branch for a project."""
        if branches is None:
            branches = await self._get_branches(project_id)

        for branch in branches:
            if branch.get("name") == "main" or branch.get("default", False):
                return branch

        raise NeonDBError(f"No main branch found in project {project_id}")

    async def _get_branch_by_name(self, project_id: str, branch_name: str) -> dict | None:
        """Get a branch by name."""
        branches = await self._get_branches(project_id)
        for branch in branches:
            if branch.get("name") == branch_name:
                return branch
        return None

    async def _create_branch(self, project_id: str, branch_name: str, parent_branch_id: str) -> dict:
        """Create a new branch."""
        payload = {
            "branch": {
                "name": branch_name,
                "parent_id": parent_branch_id,
            },
            "endpoints": [
                {"type": "read_write"}
            ]
        }
        data = await self._api_request("POST", f"/projects/{project_id}/branches", json=payload)
        logger.info(f"Created branch '{branch_name}' in project {project_id}")
        return data["branch"]

    async def _ensure_dev_branch(self, project_id: str) -> dict:
        """Ensure dev branch exists, create if not."""
        dev_branch = await self._get_branch_by_name(project_id, "dev")
        if dev_branch:
            return dev_branch

        main_branch = await self._get_main_branch(project_id)
        return await self._create_branch(project_id, "dev", main_branch["id"])

    # -------------------------------------------------------------------------
    # Database Management
    # -------------------------------------------------------------------------

    async def _get_databases(self, project_id: str, branch_id: str) -> list[dict]:
        """Get all databases in a branch."""
        data = await self._api_request(
            "GET", f"/projects/{project_id}/branches/{branch_id}/databases"
        )
        return data.get("databases", [])

    async def _get_database_count(self, project_id: str, branch_id: str) -> int:
        """Get the count of databases in a branch."""
        databases = await self._get_databases(project_id, branch_id)
        return len(databases)

    async def _create_database(
        self, project_id: str, branch_id: str, database_name: str, owner_name: str
    ) -> dict:
        """Create a database in a branch."""
        payload = {
            "database": {
                "name": database_name,
                "owner_name": owner_name,
            }
        }
        data = await self._api_request(
            "POST", f"/projects/{project_id}/branches/{branch_id}/databases", json=payload
        )
        logger.info(f"Created database '{database_name}' in branch {branch_id}")
        return data["database"]

    # -------------------------------------------------------------------------
    # Role Management
    # -------------------------------------------------------------------------

    async def _get_roles(self, project_id: str, branch_id: str) -> list[dict]:
        """Get all roles in a branch."""
        data = await self._api_request(
            "GET", f"/projects/{project_id}/branches/{branch_id}/roles"
        )
        return data.get("roles", [])

    async def _create_role(
        self, project_id: str, branch_id: str, role_name: str
    ) -> tuple[str, str]:
        """Create a role and return (role_name, password)."""
        payload = {
            "role": {
                "name": role_name,
            }
        }
        data = await self._api_request(
            "POST", f"/projects/{project_id}/branches/{branch_id}/roles", json=payload
        )
        role = data["role"]
        password = role.get("password", "")
        logger.info(f"Created role '{role_name}' in branch {branch_id}")
        return role_name, password

    # -------------------------------------------------------------------------
    # Endpoint Management
    # -------------------------------------------------------------------------

    async def _get_endpoints(self, project_id: str) -> list[dict]:
        """Get all endpoints for a project."""
        data = await self._api_request("GET", f"/projects/{project_id}/endpoints")
        return data.get("endpoints", [])

    async def _get_endpoint_for_branch(self, project_id: str, branch_id: str) -> dict | None:
        """Get the endpoint for a specific branch."""
        endpoints = await self._get_endpoints(project_id)
        for endpoint in endpoints:
            if endpoint.get("branch_id") == branch_id:
                return endpoint
        return None

    async def _ensure_endpoint_for_branch(self, project_id: str, branch_id: str) -> dict:
        """Ensure an endpoint exists for a branch, create if not."""
        endpoint = await self._get_endpoint_for_branch(project_id, branch_id)
        if endpoint:
            return endpoint

        # Create endpoint for branch
        payload = {
            "endpoint": {
                "branch_id": branch_id,
                "type": "read_write",
            }
        }
        data = await self._api_request(
            "POST", f"/projects/{project_id}/endpoints", json=payload
        )
        logger.info(f"Created endpoint for branch {branch_id}")
        return data["endpoint"]

    # -------------------------------------------------------------------------
    # Connection URI Building
    # -------------------------------------------------------------------------

    def _build_connection_uri(
        self, host: str, database_name: str, role_name: str, password: str
    ) -> str:
        """Build a PostgreSQL connection URI."""
        # URL encode the password in case it has special characters
        encoded_password = quote_plus(password)
        return f"postgresql://{role_name}:{encoded_password}@{host}/{database_name}?sslmode=require"

    async def _create_database_in_branch(
        self, project_id: str, branch: dict, database_name: str
    ) -> str:
        """
        Create role, database, and endpoint in a branch, return connection URI.

        Args:
            project_id: The NeonDB project ID
            branch: The branch dict
            database_name: Sanitized database name (also used as role name)

        Returns:
            Connection URI string
        """
        branch_id = branch["id"]
        role_name = database_name

        # Create role and database
        role_name, password = await self._create_role(project_id, branch_id, role_name)
        await self._create_database(project_id, branch_id, database_name, role_name)

        # Get or create endpoint
        endpoint = await self._ensure_endpoint_for_branch(project_id, branch_id)

        # Build and return connection URI
        return self._build_connection_uri(endpoint["host"], database_name, role_name, password)

    # -------------------------------------------------------------------------
    # Main Entry Point
    # -------------------------------------------------------------------------

    async def _find_available_project(self) -> tuple[dict, bool]:
        """
        Find a project with available capacity.
        Returns (project, is_new) tuple.

        Strategy:
        1. Get first project (projects[0]), check if it has capacity
        2. If full, create a new project
        3. If >= 100 projects, loop back from projects[-1], [-2], ... until one has capacity
        """
        projects = await self._get_managed_projects()

        if not projects:
            # No projects exist, create the first one
            new_project = await self._create_project(0)
            return new_project, True

        # Check the first project
        first_project = projects[0]
        project_id = first_project["id"]
        main_branch = await self._get_main_branch(project_id)
        db_count = await self._get_database_count(project_id, main_branch["id"])

        if db_count < MAX_DATABASES_PER_BRANCH:
            return first_project, False

        # First project is full, check if we can create a new one
        next_index = len(projects)

        if next_index < MAX_PROJECTS:
            # Create a new project
            new_project = await self._create_project(next_index)
            return new_project, True

        # Hit the limit, loop back from the end to find one with capacity
        logger.warning(f"Maximum projects ({MAX_PROJECTS}) reached, searching from end")
        for project in reversed(projects):
            project_id = project["id"]
            main_branch = await self._get_main_branch(project_id)
            db_count = await self._get_database_count(project_id, main_branch["id"])
            if db_count < MAX_DATABASES_PER_BRANCH:
                logger.info(f"Found available project: project_{project['_index']}")
                return project, False

        # All projects are full
        raise NeonDBCapacityError(
            f"All {MAX_PROJECTS} projects are full. "
            f"Total capacity ({MAX_PROJECTS * MAX_DATABASES_PER_BRANCH} databases) reached."
        )

    def _sanitize_database_name(self, database_name: str) -> str:
        """Sanitize database name to comply with PostgreSQL identifier rules."""
        safe_db_name = "".join(
            c if c.isalnum() or c == "_" else "_" for c in database_name
        ).lower()[:63]  # Max 63 chars for PostgreSQL identifiers

        if not safe_db_name or not safe_db_name[0].isalpha():
            safe_db_name = "db_" + safe_db_name

        return safe_db_name

    async def get_database_connection(self, database_name: str) -> DatabaseConnectionResult:
        """
        Create a database with the given name in prod branch only.

        This is more cost-effective as it skips dev branch creation.

        Note: Caller is responsible for ensuring idempotency (not calling twice
        with the same database_name).

        Args:
            database_name: Name for the database (e.g., "session_abc123")

        Returns:
            DatabaseConnectionResult with connection URI and metadata
        """
        if not self.neon_db_api_key:
            raise ValueError(NEON_DB_KEY_ERROR_MSG)

        import time
        start_time = time.perf_counter()

        safe_db_name = self._sanitize_database_name(database_name)
        created_at = datetime.now(timezone.utc).isoformat()

        # Acquire lock to prevent race conditions during creation
        async with self._get_creation_lock():
            # Get current project count for metadata
            all_projects = await self._get_managed_projects()
            current_project_count = len(all_projects)

            # Find or create a project with capacity
            project, is_new_project = await self._find_available_project()
            project_id = project["id"]
            project_name = project.get("name", f"project_{project.get('_index', 'unknown')}")

            # Update project count if new project was created
            if is_new_project:
                current_project_count += 1

            # Get main (prod) branch
            main_branch = await self._get_main_branch(project_id)
            branch_name = main_branch.get("name", "main")

            # Get database count before creating (for metadata)
            db_count_before = await self._get_database_count(project_id, main_branch["id"])

            # Create database in prod branch
            prod_uri = await self._create_database_in_branch(project_id, main_branch, safe_db_name)

            # Get endpoint host for metadata
            endpoint = await self._ensure_endpoint_for_branch(project_id, main_branch["id"])
            host = endpoint.get("host", "")

            # Database count after creation
            databases_in_project = db_count_before + 1
            capacity_remaining = MAX_DATABASES_PER_BRANCH - databases_in_project

            logger.info(
                f"Created prod database '{safe_db_name}' in project {project_id}",
                extra={
                    "database_name": safe_db_name,
                    "project_id": project_id,
                    "project_name": project_name,
                    "is_new_project": is_new_project,
                    "databases_in_project": databases_in_project,
                }
            )

            time_taken_ms = int((time.perf_counter() - start_time) * 1000)

            return DatabaseConnectionResult(
                connection_string=prod_uri,
                host=host,
                database_name=safe_db_name,
                original_database_name=database_name,
                role_name=safe_db_name,
                branch_name=branch_name,
                project_name=project_name,
                project_id=project_id,
                is_new_project=is_new_project,
                current_project_count=current_project_count,
                databases_in_project=databases_in_project,
                capacity_remaining=capacity_remaining,
                created_at=created_at,
                time_taken_ms=time_taken_ms,
            )

    async def get_database_connection_branches(self, database_name: str) -> DatabaseConnections:
        """
        Create a database with the given name in both dev and prod branches.

        Note: Caller is responsible for ensuring idempotency (not calling twice
        with the same database_name).

        Args:
            database_name: Name for the database (e.g., "session_abc123")

        Returns:
            DatabaseConnections with 'dev' and 'prod' connection URIs
        """
        if not self.neon_db_api_key:
            raise ValueError(NEON_DB_KEY_ERROR_MSG)

        safe_db_name = self._sanitize_database_name(database_name)

        # Acquire lock to prevent race conditions during creation
        async with self._get_creation_lock():
            # Find or create a project with capacity
            project, _ = await self._find_available_project()
            project_id = project["id"]

            # Get main branch and ensure dev branch exists
            main_branch = await self._get_main_branch(project_id)
            dev_branch = await self._ensure_dev_branch(project_id)

            # Create database in prod branch first
            prod_uri = await self._create_database_in_branch(project_id, main_branch, safe_db_name)

            # Create database in dev branch
            # If this fails, we have an inconsistent state but the prod database is usable
            try:
                dev_uri = await self._create_database_in_branch(project_id, dev_branch, safe_db_name)
            except NeonDBError as e:
                logger.error(
                    f"Failed to create dev database '{safe_db_name}' in project {project_id}. "
                    f"Prod database was created successfully. Error: {e}",
                    extra={"database_name": safe_db_name, "project_id": project_id}
                )
                raise NeonDBError(
                    f"Partial failure: prod database created but dev database failed. "
                    f"Database name: {safe_db_name}, Project: {project_id}. "
                    f"Original error: {e}"
                ) from e

            logger.info(
                f"Created database '{safe_db_name}' in project {project_id}",
                extra={"database_name": safe_db_name, "project_id": project_id}
            )

            return DatabaseConnections(dev=dev_uri, prod=prod_uri)

    # -------------------------------------------------------------------------
    # Cleanup Methods
    # -------------------------------------------------------------------------

    async def get_all_postgres_databases(self) -> list[str]:
        """Get all project IDs (for backward compatibility)."""
        projects = await self.get_all_projects()
        return [project["id"] for project in projects]

    async def delete_postgres_database(self, project_id: str) -> bool:
        """Delete a project (for backward compatibility)."""
        return await self.delete_project(project_id)


class RedisDatabaseClient(DatabaseClient):
    def __init__(self, setting: DatabaseConfig):
        self.setting = setting

    async def get_database_connection(self, database_name: str) -> DatabaseConnectionResult:
        """Get Redis connection (database_name is ignored, uses env var)."""
        import time
        start_time = time.perf_counter()

        if not os.getenv("REDIS_URL"):
            raise ValueError("REDIS_URL environment variable is not set")
        connection_string = os.getenv("REDIS_URL", "")

        time_taken_ms = int((time.perf_counter() - start_time) * 1000)

        return DatabaseConnectionResult(
            connection_string=connection_string,
            host="",  # Not applicable for env-based connection
            database_name=database_name,
            original_database_name=database_name,
            role_name="",
            branch_name="",
            project_name="redis_env",
            project_id="",
            is_new_project=False,
            current_project_count=1,
            databases_in_project=1,
            capacity_remaining=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            time_taken_ms=time_taken_ms,
        )


class MySQLDatabaseClient(DatabaseClient):
    def __init__(self, setting: DatabaseConfig):
        self.setting = setting

    async def get_database_connection(self, database_name: str) -> DatabaseConnectionResult:
        """Get MySQL connection (database_name is ignored, uses env var)."""
        import time
        start_time = time.perf_counter()

        if not os.getenv("MYSQL_URL"):
            raise ValueError("MYSQL_URL environment variable is not set")
        connection_string = os.getenv("MYSQL_URL", "")

        time_taken_ms = int((time.perf_counter() - start_time) * 1000)

        return DatabaseConnectionResult(
            connection_string=connection_string,
            host="",  # Not applicable for env-based connection
            database_name=database_name,
            original_database_name=database_name,
            role_name="",
            branch_name="",
            project_name="mysql_env",
            project_id="",
            is_new_project=False,
            current_project_count=1,
            databases_in_project=1,
            capacity_remaining=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            time_taken_ms=time_taken_ms,
        )


def create_database_client(
    database_type: str, setting: DatabaseConfig
) -> DatabaseClient:
    if database_type == "postgres":
        return PostgresDatabaseClient(setting)
    elif database_type == "redis":
        return RedisDatabaseClient(setting)
    elif database_type == "mysql":
        return MySQLDatabaseClient(setting)
    else:
        raise ValueError(f"Invalid database type: {database_type}")


if __name__ == "__main__":
    import asyncio

    async def main():
        # Test PostgreSQL with database name
        database_client = create_database_client("postgres", DatabaseConfig())
        connections = await database_client.get_database_connection("test_session_123")
        logger.info(f"PostgreSQL connections: {connections}")

        # Test Redis
        database_client = create_database_client("redis", DatabaseConfig())
        logger.info(await database_client.get_database_connection("test"))

        # Test MySQL
        database_client = create_database_client("mysql", DatabaseConfig())
        logger.info(await database_client.get_database_connection("test"))

    asyncio.run(main())
