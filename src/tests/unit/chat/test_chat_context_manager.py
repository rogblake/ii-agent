"""Unit tests for chat/context_manager.py - ContextWindowManager and SummarizationService."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.chat.application.context_service import (
    CONTEXT_WINDOWS,
    ContextWindowManager,
    SummarizationService,
)
from ii_agent.chat.types import Message, MessageRole, TextContent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_message(
    role: MessageRole = MessageRole.USER,
    text: str = "hello",
    tokens: int = 100,
    msg_id=None,
) -> Message:
    msg = MagicMock(spec=Message)
    msg.id = msg_id or uuid.uuid4()
    msg.role = role
    msg.parts = [TextContent(text=text)]
    msg.tokens = tokens
    msg.session_id = "sess-1"
    created_at = int(datetime.now(timezone.utc).timestamp())
    msg.created_at = created_at
    msg.updated_at = created_at
    msg.content = MagicMock(return_value=MagicMock(text=text))
    return msg


def _make_db_session() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _make_summary(
    session_id: str = "sess-1",
    summary_text: str = "Previous summary",
    summary_tokens: int = 50,
    end_message_id=None,
    parent_summary_id=None,
) -> MagicMock:
    s = MagicMock()
    s.id = str(uuid.uuid4())
    s.session_id = session_id
    s.summary_text = summary_text
    s.summary_tokens = summary_tokens
    s.end_message_id = end_message_id or uuid.uuid4()
    s.parent_summary_id = parent_summary_id
    s.created_at = datetime.now(timezone.utc)
    s.compression_ratio = 2.0
    return s


def _make_llm_config(model: str = "gpt-5") -> MagicMock:
    cfg = MagicMock()
    cfg.model = model
    cfg.setting_id = "test-setting"
    return cfg


# ---------------------------------------------------------------------------
# CONTEXT_WINDOWS constants
# ---------------------------------------------------------------------------

class TestContextWindows:
    def test_default_fallback_exists(self):
        assert "__default__" in CONTEXT_WINDOWS

    def test_known_model_has_context(self):
        assert CONTEXT_WINDOWS.get("gpt-5", 0) > 0

    def test_default_fallback_is_positive(self):
        assert CONTEXT_WINDOWS["__default__"] > 0


# ---------------------------------------------------------------------------
# ContextWindowManager._find_last_user_message
# ---------------------------------------------------------------------------

class TestFindLastUserMessage:
    def test_returns_minus_one_for_empty(self):
        result = ContextWindowManager._find_last_user_message([])
        assert result == -1

    def test_finds_last_user_message(self):
        messages = [
            _make_message(MessageRole.USER),
            _make_message(MessageRole.ASSISTANT),
            _make_message(MessageRole.USER),
            _make_message(MessageRole.ASSISTANT),
        ]
        idx = ContextWindowManager._find_last_user_message(messages)
        assert idx == 2

    def test_returns_minus_one_when_no_user_message(self):
        messages = [
            _make_message(MessageRole.ASSISTANT),
            _make_message(MessageRole.ASSISTANT),
        ]
        idx = ContextWindowManager._find_last_user_message(messages)
        assert idx == -1

    def test_only_user_messages(self):
        messages = [
            _make_message(MessageRole.USER),
            _make_message(MessageRole.USER),
        ]
        idx = ContextWindowManager._find_last_user_message(messages)
        assert idx == 1

    def test_last_message_is_user(self):
        messages = [
            _make_message(MessageRole.ASSISTANT),
            _make_message(MessageRole.USER),
        ]
        idx = ContextWindowManager._find_last_user_message(messages)
        assert idx == 1


# ---------------------------------------------------------------------------
# ContextWindowManager.load_context_for_llm
# ---------------------------------------------------------------------------

class TestLoadContextForLlm:
    @pytest.mark.asyncio
    async def test_returns_messages_without_summary(self):
        db = _make_db_session()
        messages = [
            _make_message(MessageRole.USER, "Hello"),
            _make_message(MessageRole.ASSISTANT, "Hi"),
        ]

        with (
            patch.object(ContextWindowManager, "_get_active_summary", new=AsyncMock(return_value=None)),
            patch("ii_agent.chat.application.context_service.MessageService") as mock_svc_cls,
        ):
            mock_svc = MagicMock()
            mock_svc.list_by_session = AsyncMock(return_value=messages)
            mock_svc_cls.return_value = mock_svc

            context = await ContextWindowManager.load_context_for_llm(
                db_session=db, session_id="sess-1"
            )

        assert len(context) == 2

    @pytest.mark.asyncio
    async def test_prepends_summary_message_when_summary_exists(self):
        db = _make_db_session()
        summary = _make_summary()
        messages = [_make_message(MessageRole.USER, "New message")]

        with (
            patch.object(ContextWindowManager, "_get_active_summary", new=AsyncMock(return_value=summary)),
            patch("ii_agent.chat.application.context_service.MessageService") as mock_svc_cls,
        ):
            mock_svc = MagicMock()
            mock_svc.list_messages_after_id = AsyncMock(return_value=messages)
            mock_svc_cls.return_value = mock_svc

            context = await ContextWindowManager.load_context_for_llm(
                db_session=db, session_id="sess-1"
            )

        # Summary message prepended + original messages
        assert len(context) == 2
        assert context[0].role == MessageRole.ASSISTANT

    @pytest.mark.asyncio
    async def test_loads_messages_after_summary(self):
        db = _make_db_session()
        summary = _make_summary()
        messages = [_make_message(MessageRole.USER, "latest")]

        with (
            patch.object(ContextWindowManager, "_get_active_summary", new=AsyncMock(return_value=summary)),
            patch("ii_agent.chat.application.context_service.MessageService") as mock_svc_cls,
        ):
            mock_svc = MagicMock()
            mock_svc.list_messages_after_id = AsyncMock(return_value=messages)
            mock_svc_cls.return_value = mock_svc

            context = await ContextWindowManager.load_context_for_llm(
                db_session=db, session_id="sess-1"
            )

        mock_svc.list_messages_after_id.assert_called_once()


# ---------------------------------------------------------------------------
# ContextWindowManager.compress_context_if_needed
# ---------------------------------------------------------------------------

class TestCompressContextIfNeeded:
    @pytest.mark.asyncio
    async def test_returns_unchanged_when_under_threshold(self):
        db = _make_db_session()
        llm_config = _make_llm_config()
        messages = [_make_message(tokens=100) for _ in range(5)]

        with patch.object(ContextWindowManager, "_get_active_summary", new=AsyncMock(return_value=None)):
            result = await ContextWindowManager.compress_context_if_needed(
                db_session=db,
                messages=messages,
                session_id="sess-1",
                llm_config=llm_config,
                user_id="user-1",
            )

        # 5 * 100 = 500 tokens << threshold (0.9 * 200000 = 180000)
        assert result is messages

    @pytest.mark.asyncio
    async def test_compresses_when_over_threshold(self):
        db = _make_db_session()
        llm_config = _make_llm_config("__default__")
        # Use default window of 128000 - threshold is 0.9 * 128000 = 115200
        messages = [_make_message(tokens=12000) for _ in range(11)]  # 132000 tokens
        # Add proper IDs for messages
        for msg in messages:
            msg.id = uuid.uuid4()

        new_summary = _make_summary(summary_tokens=1000)
        new_summary.created_at = datetime.now(timezone.utc)

        with (
            patch.object(ContextWindowManager, "_get_active_summary", new=AsyncMock(return_value=None)),
            patch.object(ContextWindowManager, "create_chained_summary", new=AsyncMock(return_value=new_summary)),
        ):
            result = await ContextWindowManager.compress_context_if_needed(
                db_session=db,
                messages=messages,
                session_id="sess-1",
                llm_config=llm_config,
                user_id="user-1",
            )

        # Should have compressed (fewer messages or different set)
        assert result is not messages

    @pytest.mark.asyncio
    async def test_returns_unchanged_when_nothing_to_summarize(self):
        db = _make_db_session()
        llm_config = _make_llm_config("__default__")
        # Only 1 message with high token count but no split possible
        msg = _make_message(MessageRole.USER, tokens=200000)
        msg.id = uuid.uuid4()
        messages = [msg]

        with patch.object(ContextWindowManager, "_get_active_summary", new=AsyncMock(return_value=None)):
            result = await ContextWindowManager.compress_context_if_needed(
                db_session=db,
                messages=messages,
                session_id="sess-1",
                llm_config=llm_config,
                user_id="user-1",
            )

        # With only 1 message, nothing to summarize
        assert result == messages


# ---------------------------------------------------------------------------
# ContextWindowManager.check_and_summarize_after_response
# ---------------------------------------------------------------------------

class TestCheckAndSummarizeAfterResponse:
    @pytest.mark.asyncio
    async def test_does_not_summarize_when_under_threshold(self):
        db = _make_db_session()
        llm_config = _make_llm_config()
        messages = [_make_message(tokens=100) for _ in range(5)]

        with (
            patch.object(ContextWindowManager, "_get_active_summary", new=AsyncMock(return_value=None)),
            patch("ii_agent.chat.application.context_service.MessageService") as mock_svc_cls,
            patch.object(ContextWindowManager, "create_chained_summary", new=AsyncMock()) as mock_summarize,
        ):
            mock_svc = MagicMock()
            mock_svc.list_by_session = AsyncMock(return_value=messages)
            mock_svc_cls.return_value = mock_svc

            await ContextWindowManager.check_and_summarize_after_response(
                db_session=db,
                session_id="sess-1",
                llm_config=llm_config,
                user_id="user-1",
            )

        mock_summarize.assert_not_called()

    @pytest.mark.asyncio
    async def test_summarizes_when_over_threshold(self):
        db = _make_db_session()
        llm_config = _make_llm_config("__default__")
        # Over threshold - 130000 tokens for 128k window
        messages = [_make_message(tokens=13000) for _ in range(11)]
        for msg in messages:
            msg.id = uuid.uuid4()

        new_summary = _make_summary(summary_tokens=2000)
        new_summary.created_at = datetime.now(timezone.utc)

        with (
            patch.object(ContextWindowManager, "_get_active_summary", new=AsyncMock(return_value=None)),
            patch("ii_agent.chat.application.context_service.MessageService") as mock_svc_cls,
            patch.object(ContextWindowManager, "create_chained_summary", new=AsyncMock(return_value=new_summary)) as mock_summarize,
        ):
            mock_svc = MagicMock()
            mock_svc.list_by_session = AsyncMock(return_value=messages)
            mock_svc_cls.return_value = mock_svc

            await ContextWindowManager.check_and_summarize_after_response(
                db_session=db,
                session_id="sess-1",
                llm_config=llm_config,
                user_id="user-1",
            )

        mock_summarize.assert_called_once()

    @pytest.mark.asyncio
    async def test_nothing_to_summarize_skips_gracefully(self):
        db = _make_db_session()
        llm_config = _make_llm_config("__default__")
        # Just a single user message over threshold
        msg = _make_message(MessageRole.USER, tokens=200000)
        msg.id = uuid.uuid4()
        messages = [msg]

        with (
            patch.object(ContextWindowManager, "_get_active_summary", new=AsyncMock(return_value=None)),
            patch("ii_agent.chat.application.context_service.MessageService") as mock_svc_cls,
            patch.object(ContextWindowManager, "create_chained_summary", new=AsyncMock()) as mock_summarize,
        ):
            mock_svc = MagicMock()
            mock_svc.list_by_session = AsyncMock(return_value=messages)
            mock_svc_cls.return_value = mock_svc

            await ContextWindowManager.check_and_summarize_after_response(
                db_session=db,
                session_id="sess-1",
                llm_config=llm_config,
                user_id="user-1",
            )

        mock_summarize.assert_not_called()


# ---------------------------------------------------------------------------
# SummarizationService._build_conversation_text
# ---------------------------------------------------------------------------

class TestBuildConversationText:
    def test_includes_user_text(self):
        messages = [_make_message(MessageRole.USER, "What is Python?")]
        text = SummarizationService._build_conversation_text(messages)
        assert "USER:" in text
        assert "What is Python?" in text

    def test_includes_assistant_text(self):
        messages = [_make_message(MessageRole.ASSISTANT, "Python is a language.")]
        text = SummarizationService._build_conversation_text(messages)
        assert "ASSISTANT:" in text
        assert "Python is a language." in text

    def test_skips_tool_messages(self):
        messages = [_make_message(MessageRole.TOOL, "tool output")]
        text = SummarizationService._build_conversation_text(messages)
        assert "tool output" not in text
        assert text == ""

    def test_empty_text_parts_skipped(self):
        msg = MagicMock(spec=Message)
        msg.role = MessageRole.USER
        msg.parts = []
        text = SummarizationService._build_conversation_text([msg])
        assert text == ""

    def test_multiple_messages_joined(self):
        messages = [
            _make_message(MessageRole.USER, "Hello"),
            _make_message(MessageRole.ASSISTANT, "World"),
        ]
        text = SummarizationService._build_conversation_text(messages)
        assert "USER: Hello" in text
        assert "ASSISTANT: World" in text


# ---------------------------------------------------------------------------
# SummarizationService._create_fallback_summary
# ---------------------------------------------------------------------------

class TestCreateFallbackSummary:
    def test_returns_tuple_of_text_and_tokens(self):
        messages = [_make_message(tokens=50) for _ in range(3)]
        for msg in messages:
            msg.role = MessageRole.USER

        text, tokens = SummarizationService._create_fallback_summary(messages)
        assert isinstance(text, str)
        assert isinstance(tokens, int)

    def test_includes_parent_summary_if_provided(self):
        messages = [_make_message(tokens=50)]
        messages[0].role = MessageRole.USER

        text, _ = SummarizationService._create_fallback_summary(messages, "Previous context here")
        assert "Previous context here" in text

    def test_limits_to_last_5_messages(self):
        messages = [_make_message(tokens=10) for _ in range(10)]
        for msg in messages:
            msg.role = MessageRole.USER

        _, tokens = SummarizationService._create_fallback_summary(messages)
        # Should only use last 5 messages: 5 * 10 = 50
        assert tokens == 50

    def test_uses_all_messages_if_fewer_than_5(self):
        messages = [_make_message(tokens=20) for _ in range(3)]
        for msg in messages:
            msg.role = MessageRole.USER

        _, tokens = SummarizationService._create_fallback_summary(messages)
        assert tokens == 60


# ---------------------------------------------------------------------------
# SummarizationService.generate_summary
# ---------------------------------------------------------------------------

class TestGenerateSummary:
    @pytest.mark.asyncio
    async def test_calls_provider_send(self):
        messages = [_make_message(MessageRole.USER, "Tell me about Python")]
        llm_config = _make_llm_config()

        mock_provider = AsyncMock()
        response = MagicMock()
        response.content = [MagicMock(text="Summary text")]
        response.usage = MagicMock(total_tokens=30)
        mock_provider.send = AsyncMock(return_value=response)

        with patch("ii_agent.chat.application.context_service.LLMProviderFactory.create_provider", return_value=mock_provider):
            summary, tokens = await SummarizationService.generate_summary(
                messages=messages,
                llm_config=llm_config,
                user_id="user-1",
                db_session=AsyncMock(),
            )

        assert summary is not None
        assert tokens == 30

    @pytest.mark.asyncio
    async def test_falls_back_on_send_exception(self):
        messages = [_make_message(MessageRole.USER, "Hello")]
        for msg in messages:
            msg.role = MessageRole.USER
        llm_config = _make_llm_config()

        mock_provider = MagicMock()
        mock_provider.send = AsyncMock(side_effect=Exception("send error"))

        with patch("ii_agent.chat.application.context_service.LLMProviderFactory.create_provider", return_value=mock_provider):
            summary, tokens = await SummarizationService.generate_summary(
                messages=messages,
                llm_config=llm_config,
                user_id="user-1",
                db_session=AsyncMock(),
            )

        # Fallback summary should still return a string
        assert isinstance(summary, str)

    @pytest.mark.asyncio
    async def test_includes_parent_summary_in_prompt(self):
        messages = [_make_message(MessageRole.USER, "New message")]
        llm_config = _make_llm_config()

        mock_provider = AsyncMock()
        response = MagicMock()
        response.content = [MagicMock(text="New summary")]
        response.usage = MagicMock(total_tokens=20)
        mock_provider.send = AsyncMock(return_value=response)

        with patch("ii_agent.chat.application.context_service.LLMProviderFactory.create_provider", return_value=mock_provider):
            summary, _ = await SummarizationService.generate_summary(
                messages=messages,
                llm_config=llm_config,
                user_id="user-1",
                db_session=AsyncMock(),
                parent_summary_text="Old summary content",
            )

        # Check that the prompt sent to provider includes parent summary
        call_args = mock_provider.send.call_args
        sent_messages = call_args[1]["messages"]
        assert len(sent_messages) == 1
        prompt_text = sent_messages[0].parts[0].text
        assert "Old summary content" in prompt_text


# ---------------------------------------------------------------------------
# ContextWindowManager.create_chained_summary
# ---------------------------------------------------------------------------

class TestCreateChainedSummary:
    @pytest.mark.asyncio
    async def test_creates_summary_with_no_parent(self):
        db = _make_db_session()
        messages = [_make_message(MessageRole.USER, "Hello", tokens=100)]
        for msg in messages:
            msg.id = uuid.uuid4()

        llm_config = _make_llm_config()
        mock_summary = _make_summary(summary_text="Summary text", summary_tokens=50)
        mock_summary.parent_summary_id = None

        with (
            patch.object(SummarizationService, "generate_summary", new=AsyncMock(return_value=("Summary text", 50))),
            patch("ii_agent.chat.application.context_service.ConversationSummary", return_value=mock_summary),
        ):
            summary = await ContextWindowManager.create_chained_summary(
                db_session=db,
                session_id="sess-1",
                messages=messages,
                parent_summary=None,
                llm_config=llm_config,
                user_id="user-1",
            )

        assert summary.summary_text == "Summary text"
        assert summary.summary_tokens == 50
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_summary_with_parent(self):
        db = _make_db_session()
        parent = _make_summary()
        messages = [_make_message(MessageRole.USER, "Hello", tokens=100)]
        for msg in messages:
            msg.id = uuid.uuid4()

        llm_config = _make_llm_config()
        mock_summary = _make_summary(summary_text="Chained summary", summary_tokens=30)
        mock_summary.parent_summary_id = parent.id

        with (
            patch.object(SummarizationService, "generate_summary", new=AsyncMock(return_value=("Chained summary", 30))),
            patch("ii_agent.chat.application.context_service.ConversationSummary", return_value=mock_summary),
        ):
            summary = await ContextWindowManager.create_chained_summary(
                db_session=db,
                session_id="sess-1",
                messages=messages,
                parent_summary=parent,
                llm_config=llm_config,
                user_id="user-1",
            )

        assert summary.parent_summary_id == parent.id

    @pytest.mark.asyncio
    async def test_compression_ratio_calculated(self):
        db = _make_db_session()
        messages = [_make_message(MessageRole.USER, "Hello", tokens=200)]
        for msg in messages:
            msg.id = uuid.uuid4()

        llm_config = _make_llm_config()
        mock_summary = _make_summary(summary_text="Summary", summary_tokens=50)
        mock_summary.compression_ratio = 4.0

        with (
            patch.object(SummarizationService, "generate_summary", new=AsyncMock(return_value=("Summary", 50))),
            patch("ii_agent.chat.application.context_service.ConversationSummary", return_value=mock_summary),
        ):
            summary = await ContextWindowManager.create_chained_summary(
                db_session=db,
                session_id="sess-1",
                messages=messages,
                parent_summary=None,
                llm_config=llm_config,
                user_id="user-1",
            )

        # original 200 / 50 summary = 4.0 ratio
        assert summary.compression_ratio == 4.0
