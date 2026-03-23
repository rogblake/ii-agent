"""FastAPI dependencies for session title generation."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.core.llm.dependencies import LLMExecutionServiceDep
from ii_agent.sessions.title_service import SessionTitleService


def get_session_title_service(
    llm_execution_service: LLMExecutionServiceDep,
) -> SessionTitleService:
    """Provide SessionTitleService instance."""
    config = get_settings().session_title
    return SessionTitleService(
        config=config,
        llm_execution_service=llm_execution_service,
    )


SessionTitleServiceDep = Annotated[SessionTitleService, Depends(get_session_title_service)]
