"""FastAPI dependencies for projects domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.engine.sandboxes.dependencies import SandboxRepositoryDep
from ii_agent.projects.repository import ProjectRepository
from ii_agent.projects.service import ProjectService
from ii_agent.projects.deployment_orchestration_service import DeploymentOrchestrationService
from ii_agent.projects.databases.service import DatabaseService
from ii_agent.projects.secrets.service import SecretService
from ii_agent.engine.sandboxes.env_sync_service import SandboxEnvSyncService
from ii_agent.sessions.dependencies import SessionRepositoryDep


# ==================== Repository Dependencies ====================


def get_project_repository() -> ProjectRepository:
    """Provide ProjectRepository instance."""
    return ProjectRepository()


ProjectRepositoryDep = Annotated[ProjectRepository, Depends(get_project_repository)]


# ==================== Service Dependencies ====================


def get_project_service(
    project_repo: ProjectRepositoryDep,
    session_repo: SessionRepositoryDep,
) -> ProjectService:
    """Provide ProjectService instance with explicit repo injection."""
    return ProjectService(
        project_repo=project_repo,
        session_repo=session_repo,
        config=get_settings(),
    )


def get_secret_service(
    project_repo: ProjectRepositoryDep,
) -> SecretService:
    """Provide SecretService instance with explicit repo injection."""
    return SecretService(project_repo=project_repo, config=get_settings())


def get_database_service(
    project_repo: ProjectRepositoryDep,
) -> DatabaseService:
    """Provide DatabaseService instance with explicit repo injection."""
    return DatabaseService(project_repo=project_repo, config=get_settings())


def get_sandbox_env_sync_service(
    session_repo: SessionRepositoryDep,
    sandbox_repo: SandboxRepositoryDep,
) -> SandboxEnvSyncService:
    """Provide SandboxEnvSyncService instance with explicit repo injection."""
    return SandboxEnvSyncService(
        session_repo=session_repo,
        sandbox_repo=sandbox_repo,
        config=get_settings(),
    )


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
SecretServiceDep = Annotated[SecretService, Depends(get_secret_service)]
DatabaseServiceDep = Annotated[DatabaseService, Depends(get_database_service)]
SandboxEnvSyncServiceDep = Annotated[SandboxEnvSyncService, Depends(get_sandbox_env_sync_service)]


def get_deployment_orchestration_service() -> DeploymentOrchestrationService:
    """Provide DeploymentOrchestrationService instance."""
    return DeploymentOrchestrationService(config=get_settings())


DeploymentOrchestrationServiceDep = Annotated[
    DeploymentOrchestrationService, Depends(get_deployment_orchestration_service)
]


__all__ = [
    "get_project_repository",
    "get_project_service",
    "get_secret_service",
    "get_database_service",
    "get_sandbox_env_sync_service",
    "get_deployment_orchestration_service",
    "ProjectRepositoryDep",
    "ProjectServiceDep",
    "SecretServiceDep",
    "DatabaseServiceDep",
    "SandboxEnvSyncServiceDep",
    "DeploymentOrchestrationServiceDep",
]
