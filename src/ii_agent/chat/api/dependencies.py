"""FastAPI dependencies for chat domain."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep, PubSubDep
from ii_agent.chat.messages.repository import ChatMessageRepository
from ii_agent.chat.messages.service import MessageService
from ii_agent.chat.application.chat_service import ChatService
from ii_agent.chat.application.file_processing_service import ChatFileProcessor
from ii_agent.chat.application.tool_service import ChatToolService
from ii_agent.chat.application.turn_loop_service import LLMTurnLoopService
from ii_agent.chat.messages.history_service import ChatMessageHistoryService

from ii_agent.settings.llm.dependencies import ModelSettingServiceDep
from ii_agent.credits.dependencies import CreditServiceDep
from ii_agent.files.dependencies import FileRepositoryDep
from ii_agent.integrations.connectors.dependencies import ConnectorRepositoryDep
from ii_agent.sessions.dependencies import SessionRepositoryDep
from ii_agent.sessions.dependencies import SessionTitleServiceDep


# ==================== Repository Dependencies ====================


def get_chat_message_repository() -> ChatMessageRepository:
    return ChatMessageRepository()


ChatMessageRepositoryDep = Annotated[ChatMessageRepository, Depends(get_chat_message_repository)]


# ==================== Services in container ====================


def _get_message_service(container: ContainerDep) -> MessageService:
    return container.message_service


MessageServiceDep = Annotated[MessageService, Depends(_get_message_service)]


# ==================== Factory-wired sub-services ====================


def get_chat_file_processor(container: ContainerDep) -> ChatFileProcessor:
    return ChatFileProcessor(config=container.config)


ChatFileProcessorDep = Annotated[ChatFileProcessor, Depends(get_chat_file_processor)]


def get_chat_tool_service(
    connector_repo: ConnectorRepositoryDep,
    container: ContainerDep,
) -> ChatToolService:
    return ChatToolService(
        connector_repo=connector_repo,
        container=container,
    )


ChatToolServiceDep = Annotated[ChatToolService, Depends(get_chat_tool_service)]


def get_chat_message_history(
    chat_repo: ChatMessageRepositoryDep,
    file_repo: FileRepositoryDep,
) -> ChatMessageHistoryService:
    return ChatMessageHistoryService(chat_repo=chat_repo, file_repo=file_repo)


ChatMessageHistoryServiceDep = Annotated[
    ChatMessageHistoryService, Depends(get_chat_message_history)
]


# ==================== ChatService ====================


def get_chat_service(
    model_setting_service: ModelSettingServiceDep,
    credit_service: CreditServiceDep,
    file_processor: ChatFileProcessorDep,
    tool_service: ChatToolServiceDep,
    message_history: ChatMessageHistoryServiceDep,
    message_service: MessageServiceDep,
    session_repo: SessionRepositoryDep,
    container: ContainerDep,
    title_service: SessionTitleServiceDep,
    pubsub: PubSubDep,
) -> ChatService:
    llm_loop = LLMTurnLoopService(message_service=message_service, pubsub=pubsub)
    return ChatService(
        file_processor=file_processor,
        tool_service=tool_service,
        llm_loop=llm_loop,
        message_history=message_history,
        message_service=message_service,
        session_repo=session_repo,
        model_setting_service=model_setting_service,
        credit_service=credit_service,
        container=container,
        title_service=title_service,
    )


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
