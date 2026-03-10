"""FastAPI dependencies for agents domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.agent.agents.repository import AgentRunTaskRepository
from ii_agent.agent.agents.agent_run_service import AgentRunService


# ==================== Repository Dependencies ====================


def get_agent_run_task_repository() -> AgentRunTaskRepository:
    """Provide AgentRunTaskRepository instance."""
    return AgentRunTaskRepository()


AgentRunTaskRepositoryDep = Annotated[AgentRunTaskRepository, Depends(get_agent_run_task_repository)]


# ==================== Service Dependencies ====================


def get_agent_run_service(
    repo: AgentRunTaskRepositoryDep,
) -> AgentRunService:
    """Provide AgentRunService instance with explicit repo injection."""
    return AgentRunService(repo=repo, config=get_settings())


AgentRunServiceDep = Annotated[AgentRunService, Depends(get_agent_run_service)]


# ── Container-only factories ─────────────────────────────────────────────────
# AgentService / ExecutionService / PlanService are only used by the
# ServiceContainer (not in routers), so no Dep aliases are needed.
# Imports are deferred to avoid the circular chain:
#   agent_service → v1.factory → … → sessions.dependencies → THIS MODULE.


def get_agent_service():
    """Provide AgentService instance (container-only)."""
    from ii_agent.core.storage.client import storage
    from ii_agent.agent.agents.agent_service import AgentService

    return AgentService(config=get_settings(), file_store=storage)


def get_execution_service():
    """Provide ExecutionService instance (container-only)."""
    from ii_agent.agent.agents.execution_service import ExecutionService

    return ExecutionService(config=get_settings())


def get_plan_service():
    """Provide PlanService instance (container-only)."""
    from ii_agent.agent.agents.plan_service import PlanService

    return PlanService(config=get_settings())


__all__ = [
    "get_agent_run_task_repository",
    "get_agent_run_service",
    "get_agent_service",
    "get_execution_service",
    "get_plan_service",
    "AgentRunTaskRepositoryDep",
    "AgentRunServiceDep",
]
