"""FastAPI dependencies for sessions domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.agent.dependencies import AgentRunServiceDep
from ii_agent.agent.sandboxes.dependencies import SandboxRepositoryDep
from ii_agent.core.events.dependencies import EventRepositoryDep
from ii_agent.sessions.repository import SessionRepository
from ii_agent.sessions.service import SessionService
from ii_agent.sessions.fork_service import SessionForkService
from ii_agent.core.storage.client import storage


# ==================== Repository Dependencies ====================


def get_session_repository() -> SessionRepository:
    """Provide SessionRepository instance."""
    return SessionRepository()


SessionRepositoryDep = Annotated[SessionRepository, Depends(get_session_repository)]


# ==================== Service Dependencies ====================


def get_session_service(
    session_repo: SessionRepositoryDep,
    event_repo: EventRepositoryDep,
    sandbox_repo: SandboxRepositoryDep,
    agent_run_service: AgentRunServiceDep,
) -> SessionService:
    """Provide SessionService instance with explicit repo injection."""
    return SessionService(
        config=get_settings(),
        session_repo=session_repo,
        event_repo=event_repo,
        agent_run_service=agent_run_service,
        file_store=storage,
        sandbox_repo=sandbox_repo,
    )


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]


def get_session_fork_service(
    session_repo: SessionRepositoryDep,
    sandbox_repo: SandboxRepositoryDep,
) -> SessionForkService:
    """Provide SessionForkService instance."""
    return SessionForkService(
        session_repo=session_repo,
        sandbox_repo=sandbox_repo,
        config=get_settings(),
    )


SessionForkServiceDep = Annotated[SessionForkService, Depends(get_session_fork_service)]
