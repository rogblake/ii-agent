"""FastAPI dependencies for sessions domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep
from ii_agent.tasks.service import RunTaskService
from ii_agent.realtime.events.repository import EventRepository
from ii_agent.sessions.repository import SessionRepository
from ii_agent.sessions.service import SessionService
from ii_agent.sessions.fork_service import SessionForkService
from ii_agent.sessions.title_service import SessionTitleService


# ==================== Repository Dependencies ====================


def get_session_repository() -> SessionRepository:
    """Provide SessionRepository instance."""
    return SessionRepository()


SessionRepositoryDep = Annotated[SessionRepository, Depends(get_session_repository)]


def get_event_repository() -> EventRepository:
    """Provide EventRepository instance."""
    return EventRepository()


EventRepositoryDep = Annotated[EventRepository, Depends(get_event_repository)]


# ==================== Service Dependencies ====================


def _get_run_task_service(container: ContainerDep) -> RunTaskService:
    return container.run_task_service


RunTaskServiceDep = Annotated[RunTaskService, Depends(_get_run_task_service)]


def _get_session_service(container: ContainerDep) -> SessionService:
    return container.session_service


SessionServiceDep = Annotated[SessionService, Depends(_get_session_service)]


def _get_session_fork_service(container: ContainerDep) -> SessionForkService:
    return container.session_fork_service


SessionForkServiceDep = Annotated[SessionForkService, Depends(_get_session_fork_service)]


def _get_session_title_service(container: ContainerDep) -> SessionTitleService:
    return container.session_title_service


SessionTitleServiceDep = Annotated[SessionTitleService, Depends(_get_session_title_service)]
