"""FastAPI dependencies for chat domain."""

from typing import Annotated

from fastapi import Depends
from starlette.requests import Request

from ii_agent.core.config.settings import get_settings
from ii_agent.core.container import ServiceContainer
from ii_agent.chat.runs.repository import ChatRunRepository
from ii_agent.chat.runs.service import ChatRunService
from ii_agent.chat.messages.repository import ChatMessageRepository
from ii_agent.chat.messages.service import MessageService
from ii_agent.chat.application.chat_service import ChatService
from ii_agent.chat.application.file_processing_service import ChatFileProcessor
from ii_agent.chat.application.tool_service import ChatToolService
from ii_agent.chat.application.turn_loop_service import LLMTurnLoopService
from ii_agent.chat.messages.history_service import ChatMessageHistoryService
from ii_agent.auth.users.dependencies import UserServiceDep
from ii_agent.settings.llm.dependencies import LLMSettingServiceDep
from ii_agent.billing.credits.dependencies import CreditServiceDep
from ii_agent.core.llm.dependencies import LLMBillingServiceDep
from ii_agent.files.dependencies import FileRepositoryDep
from ii_agent.integrations.connectors.dependencies import ConnectorRepositoryDep
from ii_agent.sessions.dependencies import SessionRepositoryDep


def get_container(request: Request) -> ServiceContainer:
    """Provide ServiceContainer from app state."""
    return request.app.state.container


ContainerDep = Annotated[ServiceContainer, Depends(get_container)]


# ==================== Repository Dependencies ====================


def get_chat_message_repository() -> ChatMessageRepository:
    """Provide ChatMessageRepository instance."""
    return ChatMessageRepository()


ChatMessageRepositoryDep = Annotated[ChatMessageRepository, Depends(get_chat_message_repository)]


def get_message_service() -> MessageService:
    """Provide MessageService instance."""
    return MessageService()


MessageServiceDep = Annotated[MessageService, Depends(get_message_service)]


# ==================== Sub-service Dependencies ====================


def get_chat_file_processor() -> ChatFileProcessor:
    """Provide ChatFileProcessor instance."""
    return ChatFileProcessor(config=get_settings())


ChatFileProcessorDep = Annotated[ChatFileProcessor, Depends(get_chat_file_processor)]


def get_chat_tool_service(
    user_service: UserServiceDep,
    connector_repo: ConnectorRepositoryDep,
    container: ContainerDep,
) -> ChatToolService:
    """Provide ChatToolService instance."""
    return ChatToolService(
        user_service=user_service,
        connector_repo=connector_repo,
        container=container,
        config=get_settings(),
    )


ChatToolServiceDep = Annotated[ChatToolService, Depends(get_chat_tool_service)]


def get_chat_message_history(
    chat_repo: ChatMessageRepositoryDep,
    file_repo: FileRepositoryDep,
) -> ChatMessageHistoryService:
    """Provide ChatMessageHistoryService instance."""
    return ChatMessageHistoryService(chat_repo=chat_repo, file_repo=file_repo)


ChatMessageHistoryServiceDep = Annotated[ChatMessageHistoryService, Depends(get_chat_message_history)]


def get_llm_loop_service(
    llm_billing: LLMBillingServiceDep,
    message_service: MessageServiceDep,
) -> LLMTurnLoopService:
    """Provide LLMTurnLoopService instance."""
    return LLMTurnLoopService(message_service=message_service, llm_billing=llm_billing)


LLMTurnLoopServiceDep = Annotated[LLMTurnLoopService, Depends(get_llm_loop_service)]


# ==================== Chat Run Dependencies ====================


def get_chat_run_repository() -> ChatRunRepository:
    """Provide ChatRunRepository instance."""
    return ChatRunRepository()


ChatRunRepositoryDep = Annotated[ChatRunRepository, Depends(get_chat_run_repository)]


def get_chat_run_service(repo: ChatRunRepositoryDep) -> ChatRunService:
    """Provide ChatRunService instance."""
    return ChatRunService(repo=repo)


ChatRunServiceDep = Annotated[ChatRunService, Depends(get_chat_run_service)]


# ==================== Service Dependencies ====================


def get_chat_service(
    llm_setting_service: LLMSettingServiceDep,
    credit_service: CreditServiceDep,
    file_processor: ChatFileProcessorDep,
    tool_service: ChatToolServiceDep,
    llm_loop: LLMTurnLoopServiceDep,
    message_history: ChatMessageHistoryServiceDep,
    message_service: MessageServiceDep,
    chat_run_service: ChatRunServiceDep,
    session_repo: SessionRepositoryDep,
    container: ContainerDep,
) -> ChatService:
    """Provide ChatService instance with explicit sub-service injection."""
    return ChatService(
        file_processor=file_processor,
        tool_service=tool_service,
        llm_loop=llm_loop,
        message_history=message_history,
        message_service=message_service,
        session_repo=session_repo,
        chat_run_service=chat_run_service,
        llm_setting_service=llm_setting_service,
        credit_service=credit_service,
        container=container,
    )


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
