"""FastAPI dependencies for chat runs domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.chat.runs.repository import ChatRunRepository
from ii_agent.chat.runs.service import ChatRunService


def get_chat_run_repository() -> ChatRunRepository:
    """Provide ChatRunRepository instance."""
    return ChatRunRepository()


ChatRunRepositoryDep = Annotated[ChatRunRepository, Depends(get_chat_run_repository)]


def get_chat_run_service(repo: ChatRunRepositoryDep) -> ChatRunService:
    """Provide ChatRunService instance."""
    return ChatRunService(repo=repo)


ChatRunServiceDep = Annotated[ChatRunService, Depends(get_chat_run_service)]
