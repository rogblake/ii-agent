"""Project and deployment management domain module.

Public API re-exports are declared in ``__all__`` but use lazy imports
to avoid circular-import chains at module load time.
"""

__all__ = [
    # Models
    "Project",
    # Repository
    "ProjectRepository",
    # Service
    "ProjectService",
    "DeploymentOrchestrationService",
    "DeploymentContext",
    # Schemas
    "SessionProjectResponse",
    # Exceptions
    "ProjectNotFoundError",
]


def __getattr__(name: str):  # noqa: ANN001
    """Lazy imports to avoid circular dependency chains."""
    if name == "Project":
        from ii_agent.projects.models import Project

        return Project
    if name == "ProjectRepository":
        from ii_agent.projects.repository import ProjectRepository

        return ProjectRepository
    if name == "ProjectService":
        from ii_agent.projects.service import ProjectService

        return ProjectService
    if name in ("DeploymentOrchestrationService", "DeploymentContext"):
        from ii_agent.projects import deployment_orchestration_service as _mod

        return getattr(_mod, name)
    if name == "SessionProjectResponse":
        from ii_agent.projects.schemas import SessionProjectResponse

        return SessionProjectResponse
    if name == "ProjectNotFoundError":
        from ii_agent.projects.exceptions import ProjectNotFoundError

        return ProjectNotFoundError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
