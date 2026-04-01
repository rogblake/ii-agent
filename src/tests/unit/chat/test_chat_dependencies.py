"""Unit tests for chat/dependencies.py.

Verifies that factory functions return correct service instances with
expected dependencies injected.  External services are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ii_agent.chat.api.dependencies import (
    get_chat_file_processor,
    get_chat_message_history,
    get_chat_message_repository,
    get_chat_service,
    get_chat_tool_service,
    _get_message_service as get_message_service,
)
from ii_agent.core.dependencies import _get_container as get_container
from ii_agent.chat.application.file_processing_service import ChatFileProcessor
from ii_agent.chat.application.turn_loop_service import LLMTurnLoopService
from ii_agent.chat.messages.history_service import ChatMessageHistoryService
from ii_agent.chat.messages.service import MessageService
from ii_agent.chat.messages.repository import ChatMessageRepository
from ii_agent.chat.application.chat_service import ChatService
from ii_agent.chat.application.tool_service import ChatToolService


# ---------------------------------------------------------------------------
# get_container
# ---------------------------------------------------------------------------


class TestGetContainer:
    def test_returns_app_state_container(self):
        container = MagicMock()
        request = MagicMock()
        request.app.state.container = container

        result = get_container(request)
        assert result is container

    def test_different_requests_return_their_own_containers(self):
        container_a = MagicMock()
        container_b = MagicMock()

        req_a = MagicMock()
        req_a.app.state.container = container_a

        req_b = MagicMock()
        req_b.app.state.container = container_b

        assert get_container(req_a) is container_a
        assert get_container(req_b) is container_b


# ---------------------------------------------------------------------------
# get_chat_message_repository
# ---------------------------------------------------------------------------


class TestGetChatMessageRepository:
    def test_returns_chat_message_repository_instance(self):
        result = get_chat_message_repository()
        assert isinstance(result, ChatMessageRepository)

    def test_returns_new_instance_each_call(self):
        a = get_chat_message_repository()
        b = get_chat_message_repository()
        assert a is not b


# ---------------------------------------------------------------------------
# get_message_service
# ---------------------------------------------------------------------------


class TestGetMessageService:
    def test_returns_container_message_service(self):
        mock_container = MagicMock()
        mock_container.message_service = MagicMock(spec=MessageService)
        result = get_message_service(mock_container)
        assert result is mock_container.message_service


# ---------------------------------------------------------------------------
# get_chat_file_processor
# ---------------------------------------------------------------------------


class TestGetChatFileProcessor:
    def test_returns_chat_file_processor_instance(self):
        mock_container = MagicMock()
        result = get_chat_file_processor(mock_container)
        assert isinstance(result, ChatFileProcessor)

    def test_config_injected_into_processor(self):
        mock_container = MagicMock()
        result = get_chat_file_processor(mock_container)
        assert result._config is mock_container.config


# ---------------------------------------------------------------------------
# get_chat_tool_service
# ---------------------------------------------------------------------------


class TestGetChatToolService:
    def test_returns_chat_tool_service_instance(self):
        mock_connector_repo = MagicMock()
        mock_container = MagicMock()

        result = get_chat_tool_service(
            connector_repo=mock_connector_repo,
            container=mock_container,
        )

        assert isinstance(result, ChatToolService)

    def test_dependencies_stored_in_service(self):
        mock_connector_repo = MagicMock()
        mock_container = MagicMock()

        result = get_chat_tool_service(
            connector_repo=mock_connector_repo,
            container=mock_container,
        )

        # Check that the service received the mocked dependencies
        assert result._connector_repo is mock_connector_repo
        assert result._container is mock_container


# ---------------------------------------------------------------------------
# get_chat_message_history
# ---------------------------------------------------------------------------


class TestGetChatMessageHistory:
    def test_returns_chat_message_history_service_instance(self):
        mock_chat_repo = MagicMock()
        mock_file_repo = MagicMock()

        result = get_chat_message_history(
            chat_repo=mock_chat_repo,
            file_repo=mock_file_repo,
        )

        assert isinstance(result, ChatMessageHistoryService)

    def test_repos_stored_in_service(self):
        mock_chat_repo = MagicMock()
        mock_file_repo = MagicMock()

        result = get_chat_message_history(
            chat_repo=mock_chat_repo,
            file_repo=mock_file_repo,
        )

        assert result._repo is mock_chat_repo
        assert result._file_repo is mock_file_repo


# ---------------------------------------------------------------------------
# get_chat_service
# ---------------------------------------------------------------------------


class TestGetChatService:
    def _make_mocks(self):
        return {
            "model_setting_service": MagicMock(),
            "credit_service": MagicMock(),
            "file_processor": MagicMock(),
            "tool_service": MagicMock(),
            "message_history": MagicMock(),
            "message_service": MagicMock(),
            "session_repo": MagicMock(),
            "container": MagicMock(),
            "title_service": MagicMock(),
        }

    def test_returns_chat_service_instance(self):
        mocks = self._make_mocks()
        result = get_chat_service(**mocks)
        assert isinstance(result, ChatService)

    def test_all_dependencies_wired(self):
        mocks = self._make_mocks()
        result = get_chat_service(**mocks)

        assert result._file_processor is mocks["file_processor"]
        assert result._tool_service is mocks["tool_service"]
        assert result._message_history is mocks["message_history"]
        assert result._message_service is mocks["message_service"]
        assert result._session_repo is mocks["session_repo"]
        assert result._model_setting_service is mocks["model_setting_service"]
        assert result._credit_service is mocks["credit_service"]
        assert result._container is mocks["container"]
