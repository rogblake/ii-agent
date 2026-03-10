"""Unit tests for chat service, file processor, file_processing_service."""
from __future__ import annotations

import io
import json
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.unit


# ============================================================================
# Helpers
# ============================================================================


def _make_settings():
    return SimpleNamespace(
        workspace_path="/workspace",
        tool_server_url="http://tool-server",
    )


def _make_file_upload(
    *,
    file_id="file-001",
    file_name="test.txt",
    file_size=1024,
    content_type="text/plain",
    storage_path="uploads/test.txt",
):
    return SimpleNamespace(
        id=file_id,
        file_name=file_name,
        file_size=file_size,
        content_type=content_type,
        storage_path=storage_path,
    )


# ============================================================================
# file_processor - helper functions
# ============================================================================


class TestIsBinaryFile:
    def test_pdf_is_binary(self):
        from ii_agent.chat.application.file_processor import is_binary_file

        assert is_binary_file("application/pdf", "file.pdf")

    def test_image_png_is_binary(self):
        from ii_agent.chat.application.file_processor import is_binary_file

        assert is_binary_file("image/png", "file.png")

    def test_image_jpeg_is_binary(self):
        from ii_agent.chat.application.file_processor import is_binary_file

        assert is_binary_file("image/jpeg", "file.jpg")

    def test_text_plain_not_binary(self):
        from ii_agent.chat.application.file_processor import is_binary_file

        assert not is_binary_file("text/plain", "file.txt")

    def test_application_json_not_binary(self):
        from ii_agent.chat.application.file_processor import is_binary_file

        assert not is_binary_file("application/json", "file.json")

    def test_no_content_type_pdf_extension(self):
        from ii_agent.chat.application.file_processor import is_binary_file

        assert is_binary_file(None, "file.pdf")

    def test_no_content_type_png_extension(self):
        from ii_agent.chat.application.file_processor import is_binary_file

        assert is_binary_file(None, "file.png")

    def test_no_content_type_txt_not_binary(self):
        from ii_agent.chat.application.file_processor import is_binary_file

        assert not is_binary_file(None, "file.txt")


class TestIsRemoteUrl:
    def test_http_url(self):
        from ii_agent.chat.application.file_processor import is_remote_url

        assert is_remote_url("http://example.com/file.pdf")

    def test_https_url(self):
        from ii_agent.chat.application.file_processor import is_remote_url

        assert is_remote_url("https://example.com/file.pdf")

    def test_local_path_not_url(self):
        from ii_agent.chat.application.file_processor import is_remote_url

        assert not is_remote_url("uploads/test.pdf")

    def test_sessions_path_not_url(self):
        from ii_agent.chat.application.file_processor import is_remote_url

        assert not is_remote_url("sessions/sess-1/file.png")


class TestIsTextExtractable:
    def test_txt_file_extractable(self):
        from ii_agent.chat.application.file_processor import is_text_extractable

        assert is_text_extractable("text/plain", "file.txt")

    def test_json_file_extractable(self):
        from ii_agent.chat.application.file_processor import is_text_extractable

        assert is_text_extractable("application/json", "file.json")

    def test_pdf_not_extractable(self):
        from ii_agent.chat.application.file_processor import is_text_extractable

        # PDF extractor is commented out, so PDF is not text-extractable
        assert not is_text_extractable("application/pdf", "file.pdf")

    def test_csv_extractable(self):
        from ii_agent.chat.application.file_processor import is_text_extractable

        assert is_text_extractable("text/csv", "file.csv")

    def test_python_file_by_extension(self):
        from ii_agent.chat.application.file_processor import is_text_extractable

        assert is_text_extractable(None, "script.py")

    def test_image_not_extractable(self):
        from ii_agent.chat.application.file_processor import is_text_extractable

        assert not is_text_extractable("image/png", "file.png")

    def test_docx_extractable(self):
        from ii_agent.chat.application.file_processor import is_text_extractable

        assert is_text_extractable(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "file.docx",
        )


# ============================================================================
# ContentExtractorFactory
# ============================================================================


class TestContentExtractorFactory:
    def test_get_extractor_for_text_plain(self):
        from ii_agent.chat.application.file_processor import (
            ContentExtractorFactory,
            TextExtractor,
        )

        extractor = ContentExtractorFactory.get_extractor("text/plain", "file.txt")
        assert isinstance(extractor, TextExtractor)

    def test_get_extractor_for_json(self):
        from ii_agent.chat.application.file_processor import (
            ContentExtractorFactory,
            JSONExtractor,
        )

        extractor = ContentExtractorFactory.get_extractor("application/json", "file.json")
        assert isinstance(extractor, JSONExtractor)

    def test_get_extractor_for_csv(self):
        from ii_agent.chat.application.file_processor import (
            ContentExtractorFactory,
            CSVExtractor,
        )

        extractor = ContentExtractorFactory.get_extractor("text/csv", "file.csv")
        assert isinstance(extractor, CSVExtractor)

    def test_get_extractor_by_extension_py(self):
        from ii_agent.chat.application.file_processor import (
            ContentExtractorFactory,
            CodeExtractor,
        )

        extractor = ContentExtractorFactory.get_extractor(None, "script.py")
        assert isinstance(extractor, CodeExtractor)

    def test_get_extractor_by_extension_md(self):
        from ii_agent.chat.application.file_processor import (
            ContentExtractorFactory,
            MarkdownExtractor,
        )

        extractor = ContentExtractorFactory.get_extractor(None, "readme.md")
        assert isinstance(extractor, MarkdownExtractor)

    def test_get_extractor_unknown_returns_none(self):
        from ii_agent.chat.application.file_processor import ContentExtractorFactory

        extractor = ContentExtractorFactory.get_extractor(None, "unknown.xyz")
        assert extractor is None

    def test_extract_content_returns_none_for_unknown(self):
        from ii_agent.chat.application.file_processor import ContentExtractorFactory

        result = ContentExtractorFactory.extract_content(io.BytesIO(b""), None, "file.xyz")
        assert result is None

    def test_extract_content_for_text_file(self):
        from ii_agent.chat.application.file_processor import ContentExtractorFactory

        file_obj = io.BytesIO(b"Hello World")
        result = ContentExtractorFactory.extract_content(file_obj, "text/plain", "file.txt")
        assert result == "Hello World"


# ============================================================================
# TextExtractor
# ============================================================================


class TestTextExtractor:
    def test_extracts_plain_text(self):
        from ii_agent.chat.application.file_processor import TextExtractor

        extractor = TextExtractor()
        file_obj = io.BytesIO(b"Hello, World!")
        result = extractor.extract(file_obj)
        assert result == "Hello, World!"

    def test_handles_utf8(self):
        from ii_agent.chat.application.file_processor import TextExtractor

        extractor = TextExtractor()
        file_obj = io.BytesIO("Héllo Wörld".encode("utf-8"))
        result = extractor.extract(file_obj)
        assert "H" in result

    def test_returns_none_on_error(self):
        from ii_agent.chat.application.file_processor import TextExtractor

        extractor = TextExtractor()
        bad_obj = MagicMock()
        bad_obj.seek.side_effect = Exception("IO Error")
        result = extractor.extract(bad_obj)
        assert result is None


class TestMarkdownExtractor:
    def test_extracts_markdown_content(self):
        from ii_agent.chat.application.file_processor import MarkdownExtractor

        extractor = MarkdownExtractor()
        file_obj = io.BytesIO(b"# Title\n\nContent here")
        result = extractor.extract(file_obj)
        assert "# Title" in result


class TestCodeExtractor:
    def test_extracts_python_code(self):
        from ii_agent.chat.application.file_processor import CodeExtractor

        extractor = CodeExtractor()
        code = b"def hello():\n    print('hello')"
        file_obj = io.BytesIO(code)
        result = extractor.extract(file_obj)
        assert "def hello" in result

    def test_fallback_to_latin1(self):
        from ii_agent.chat.application.file_processor import CodeExtractor

        extractor = CodeExtractor()
        # Bytes that are not valid UTF-8
        file_obj = io.BytesIO(b"\xff\xfe some code")
        result = extractor.extract(file_obj)
        assert result is not None


class TestJSONExtractor:
    def test_pretty_prints_valid_json(self):
        from ii_agent.chat.application.file_processor import JSONExtractor

        extractor = JSONExtractor()
        data = json.dumps({"key": "value"}).encode("utf-8")
        file_obj = io.BytesIO(data)
        result = extractor.extract(file_obj)
        assert '"key"' in result
        assert "value" in result

    def test_handles_invalid_json(self):
        from ii_agent.chat.application.file_processor import JSONExtractor

        extractor = JSONExtractor()
        file_obj = io.BytesIO(b"not json at all {{{{")
        result = extractor.extract(file_obj)
        assert result is not None  # returns raw content


class TestCSVExtractor:
    def test_extracts_small_csv(self):
        from ii_agent.chat.application.file_processor import CSVExtractor

        extractor = CSVExtractor()
        csv_data = b"name,age\nAlice,30\nBob,25"
        file_obj = io.BytesIO(csv_data)
        result = extractor.extract(file_obj)
        assert "name" in result
        assert "Alice" in result

    def test_returns_none_for_empty_csv(self):
        from ii_agent.chat.application.file_processor import CSVExtractor

        extractor = CSVExtractor()
        file_obj = io.BytesIO(b"")
        result = extractor.extract(file_obj)
        assert result is None


class TestXMLExtractor:
    def test_extracts_and_formats_xml(self):
        from ii_agent.chat.application.file_processor import XMLExtractor

        extractor = XMLExtractor()
        xml_data = b"<root><item>value</item></root>"
        file_obj = io.BytesIO(xml_data)
        result = extractor.extract(file_obj)
        assert result is not None
        assert "value" in result

    def test_handles_invalid_xml(self):
        from ii_agent.chat.application.file_processor import XMLExtractor

        extractor = XMLExtractor()
        file_obj = io.BytesIO(b"<not><valid xml")
        result = extractor.extract(file_obj)
        # Returns raw content on parse error
        assert result is not None


# ============================================================================
# process_files_for_message
# ============================================================================


class TestProcessFilesForMessage:
    @pytest.mark.asyncio
    async def test_process_files_structure_has_expected_fields(self):
        from ii_agent.chat.application.file_processor import ProcessedFiles

        processed = ProcessedFiles(
            binary_parts=[],
            text_parts=[],
            large_file_ids=set(),
            large_file_info=[],
            skipped_files=[],
        )
        assert processed.binary_parts == []
        assert processed.text_parts == []
        assert processed.large_file_ids == set()
        assert processed.skipped_files == []

    @pytest.mark.asyncio
    async def test_large_file_goes_to_large_file_ids(self):
        from ii_agent.chat.application.file_processor import process_files_for_message

        # 51MB file
        large_file = _make_file_upload(
            file_id="large-file",
            file_size=51 * 1024 * 1024,
            content_type="text/plain",
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [large_file]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await process_files_for_message(
            db_session=db,
            file_ids=["large-file"],
            storage=MagicMock(),
            session_id="sess-001",
        )
        assert "large-file" in result.large_file_ids

    @pytest.mark.asyncio
    async def test_unsupported_file_goes_to_skipped(self):
        from ii_agent.chat.application.file_processor import process_files_for_message

        unsupported = _make_file_upload(
            file_id="unsupported",
            file_name="file.xyz",
            content_type="application/xyz",
            file_size=1024,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [unsupported]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await process_files_for_message(
            db_session=db,
            file_ids=["unsupported"],
            storage=MagicMock(),
            session_id="sess-001",
        )
        assert len(result.skipped_files) == 1


# ============================================================================
# ChatFileProcessor
# ============================================================================


class TestChatFileProcessor:
    def _make_processor(self):
        from ii_agent.chat.application.file_processing_service import ChatFileProcessor

        return ChatFileProcessor(config=_make_settings())

    @pytest.mark.asyncio
    async def test_process_uploads_no_files_returns_none(self):
        processor = self._make_processor()
        user_message = SimpleNamespace(
            id="msg-1",
            session_id="sess-1",
            role="user",
            parts=[SimpleNamespace(text="hello")],
            file_ids=[],
            model=None,
            provider=None,
            created_at=None,
            updated_at=None,
            tokens=None,
            tools_enabled=None,
            metadata=None,
            provider_metadata=None,
            finish_reason=None,
        )

        result = await processor.process_uploads(
            AsyncMock(),
            user_id="user-1",
            session_id="sess-1",
            user_message=user_message,
            llm_content="hello",
            display_content="hello",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_process_uploads_no_files_updates_parts_when_content_differs(self):
        from ii_agent.chat.types import TextContent

        processor = self._make_processor()
        text_part = TextContent(text="display content")
        user_message = SimpleNamespace(
            id="msg-1",
            session_id="sess-1",
            role="user",
            parts=[text_part],
            file_ids=[],
            model=None,
            provider=None,
            created_at=None,
            updated_at=None,
            tokens=None,
            tools_enabled=None,
            metadata=None,
            provider_metadata=None,
            finish_reason=None,
        )

        await processor.process_uploads(
            AsyncMock(),
            user_id="user-1",
            session_id="sess-1",
            user_message=user_message,
            llm_content="llm content with extra",
            display_content="display content",
        )
        # The text part should be updated to llm_content
        assert user_message.parts[0].text == "llm content with extra"

    @pytest.mark.asyncio
    async def test_process_uploads_with_binary_files_extends_parts(self):
        from ii_agent.chat.application.file_processing_service import ChatFileProcessor
        from ii_agent.chat.types import TextContent, BinaryContent

        processor = ChatFileProcessor(config=_make_settings())

        text_part = TextContent(text="hello")
        user_message = SimpleNamespace(
            parts=[text_part],
            file_ids=["file-1"],
        )

        from ii_agent.chat.application.file_processor import ProcessedFiles

        processed = ProcessedFiles(
            binary_parts=[BinaryContent(path="uploads/img.png", mime_type="image/png", data=b"png")],
            text_parts=[],
            large_file_ids=set(),
            large_file_info=[],
            skipped_files=[],
        )

        with patch(
            "ii_agent.chat.application.file_processing_service.process_files_for_message",
            new=AsyncMock(return_value=processed),
        ):
            await processor.process_uploads(
                AsyncMock(),
                user_id="user-1",
                session_id="sess-1",
                user_message=user_message,
                llm_content="hello",
                display_content="hello",
            )
        # Should have appended binary part
        assert len(user_message.parts) == 2

    @pytest.mark.asyncio
    async def test_process_uploads_with_text_files_appends_to_text_part(self):
        from ii_agent.chat.application.file_processing_service import ChatFileProcessor
        from ii_agent.chat.types import TextContent

        processor = ChatFileProcessor(config=_make_settings())

        text_part = TextContent(text="user query")
        user_message = SimpleNamespace(
            parts=[text_part],
            file_ids=["file-1"],
        )

        from ii_agent.chat.application.file_processor import ProcessedFiles

        processed = ProcessedFiles(
            binary_parts=[],
            text_parts=[TextContent(text="\n\n--- File: test.txt ---\nfile content\n--- End of test.txt ---\n")],
            large_file_ids=set(),
            large_file_info=[],
            skipped_files=[],
        )

        with patch(
            "ii_agent.chat.application.file_processing_service.process_files_for_message",
            new=AsyncMock(return_value=processed),
        ):
            await processor.process_uploads(
                AsyncMock(),
                user_id="user-1",
                session_id="sess-1",
                user_message=user_message,
                llm_content="user query",
                display_content="user query",
            )
        # The parts[0] text should include a summary of what was extracted
        assert "text file" in user_message.parts[0].text
        assert "user query" in user_message.parts[0].text

    @pytest.mark.asyncio
    async def test_process_uploads_with_large_files_calls_vector_store(self):
        from ii_agent.chat.application.file_processing_service import ChatFileProcessor
        from ii_agent.chat.types import TextContent

        processor = ChatFileProcessor(config=_make_settings())

        text_part = TextContent(text="user query")
        user_message = SimpleNamespace(
            parts=[text_part],
            file_ids=["big-file"],
        )

        from ii_agent.chat.application.file_processor import ProcessedFiles

        processed = ProcessedFiles(
            binary_parts=[],
            text_parts=[],
            large_file_ids={"big-file"},
            large_file_info=[{"file_name": "big.pdf", "size_kb": "51200.00"}],
            skipped_files=[],
        )

        mock_vs = AsyncMock()
        mock_vs.retrieve = AsyncMock(return_value=SimpleNamespace(id="vs-1"))
        mock_vs.add_files_batch = AsyncMock(return_value=[SimpleNamespace(id="vsf-1")])

        with patch(
            "ii_agent.chat.application.file_processing_service.process_files_for_message",
            new=AsyncMock(return_value=processed),
        ), patch(
            "ii_agent.chat.application.file_processing_service.openai_vector_store",
            mock_vs,
        ):
            vector_store = await processor.process_uploads(
                AsyncMock(),
                user_id="user-1",
                session_id="sess-1",
                user_message=user_message,
                llm_content="user query",
                display_content="user query",
            )
        mock_vs.retrieve.assert_called_once()
        mock_vs.add_files_batch.assert_called_once()


# ============================================================================
# ChatService - _truncate_session_name
# ============================================================================


class TestChatServiceTruncateSessionName:
    def _make_service(self):
        from ii_agent.chat.application.chat_service import ChatService

        return ChatService(
            file_processor=SimpleNamespace(_config=_make_settings()),
            tool_service=SimpleNamespace(),
            llm_loop=SimpleNamespace(),
            message_history=SimpleNamespace(),
            message_service=SimpleNamespace(),
            session_repo=SimpleNamespace(),
            chat_run_service=SimpleNamespace(),
            llm_setting_service=SimpleNamespace(),
            credit_service=None,
            container=SimpleNamespace(),
        )

    def test_short_query_unchanged(self):
        service = self._make_service()
        result = service._truncate_session_name("Hello", max_length=50)
        assert result == "Hello"

    def test_long_query_truncated_with_ellipsis(self):
        service = self._make_service()
        result = service._truncate_session_name("x" * 60, max_length=50)
        assert result.endswith("...")
        assert len(result) == 53

    def test_exact_max_length_not_truncated(self):
        service = self._make_service()
        result = service._truncate_session_name("x" * 50, max_length=50)
        assert not result.endswith("...")
        assert len(result) == 50

    def test_empty_string_stays_empty(self):
        service = self._make_service()
        result = service._truncate_session_name("", max_length=50)
        assert result == ""


# ============================================================================
# ChatService - validate_session_access
# ============================================================================


class TestChatServiceValidateSessionAccess:
    def _make_service(self, session=None):
        from ii_agent.chat.application.chat_service import ChatService

        class FakeRepo:
            def __init__(self, s):
                self._session = s

            async def get_by_id(self, db, session_id):
                return self._session

        return ChatService(
            file_processor=SimpleNamespace(_config=_make_settings()),
            tool_service=SimpleNamespace(),
            llm_loop=SimpleNamespace(),
            message_history=SimpleNamespace(),
            message_service=SimpleNamespace(),
            session_repo=FakeRepo(session),
            chat_run_service=SimpleNamespace(),
            llm_setting_service=SimpleNamespace(),
            credit_service=None,
            container=SimpleNamespace(),
        )

    @pytest.mark.asyncio
    async def test_raises_for_missing_session(self):
        from ii_agent.sessions.exceptions import SessionNotFoundError

        service = self._make_service(session=None)
        with pytest.raises(SessionNotFoundError):
            await service.validate_session_access(
                AsyncMock(), session_id="s1", user_id="u1"
            )

    @pytest.mark.asyncio
    async def test_raises_for_wrong_user(self):
        from ii_agent.sessions.exceptions import SessionNotFoundError

        session = SimpleNamespace(user_id="other-user")
        service = self._make_service(session=session)
        with pytest.raises(SessionNotFoundError):
            await service.validate_session_access(
                AsyncMock(), session_id="s1", user_id="u1"
            )

    @pytest.mark.asyncio
    async def test_passes_for_correct_user(self):
        session = SimpleNamespace(user_id="u1")
        service = self._make_service(session=session)
        # Should not raise
        await service.validate_session_access(
            AsyncMock(), session_id="s1", user_id="u1"
        )


# ============================================================================
# ChatService - check_sufficient_credits
# ============================================================================


class TestChatServiceCheckSufficientCredits:
    def _make_service(self, credit_service=None):
        from ii_agent.chat.application.chat_service import ChatService

        return ChatService(
            file_processor=SimpleNamespace(_config=_make_settings()),
            tool_service=SimpleNamespace(),
            llm_loop=SimpleNamespace(),
            message_history=SimpleNamespace(),
            message_service=SimpleNamespace(),
            session_repo=SimpleNamespace(),
            chat_run_service=SimpleNamespace(),
            llm_setting_service=SimpleNamespace(),
            credit_service=credit_service,
            container=SimpleNamespace(),
        )

    @pytest.mark.asyncio
    async def test_returns_true_when_no_credit_service(self):
        service = self._make_service(credit_service=None)
        result = await service.check_sufficient_credits(AsyncMock(), user_id="u1")
        assert result is True

    @pytest.mark.asyncio
    async def test_delegates_to_credit_service(self):
        credit_service = AsyncMock()
        credit_service.has_sufficient = AsyncMock(return_value=True)
        service = self._make_service(credit_service=credit_service)
        result = await service.check_sufficient_credits(AsyncMock(), user_id="u1")
        assert result is True
        credit_service.has_sufficient.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_insufficient(self):
        credit_service = AsyncMock()
        credit_service.has_sufficient = AsyncMock(return_value=False)
        service = self._make_service(credit_service=credit_service)
        result = await service.check_sufficient_credits(AsyncMock(), user_id="u1")
        assert result is False


# ============================================================================
# ChatService - validate_model_for_chat
# ============================================================================


class TestChatServiceValidateModelForChat:
    def _make_service(self, models=None):
        from ii_agent.chat.application.chat_service import ChatService

        class FakeLLMSettingService:
            async def get_all_available_models(self, db, user_id):
                return SimpleNamespace(models=models or [])

        return ChatService(
            file_processor=SimpleNamespace(_config=_make_settings()),
            tool_service=SimpleNamespace(),
            llm_loop=SimpleNamespace(),
            message_history=SimpleNamespace(),
            message_service=SimpleNamespace(),
            session_repo=SimpleNamespace(),
            chat_run_service=SimpleNamespace(),
            llm_setting_service=FakeLLMSettingService(),
            credit_service=None,
            container=SimpleNamespace(),
        )

    @pytest.mark.asyncio
    async def test_raises_for_unknown_model(self):
        from ii_agent.chat.exceptions import ModelNotFoundError

        service = self._make_service(models=[])
        with pytest.raises(ModelNotFoundError):
            await service.validate_model_for_chat(
                AsyncMock(), model_id="unknown-model", user_id="u1"
            )

    @pytest.mark.asyncio
    async def test_passes_for_known_model(self):
        model = SimpleNamespace(id="claude-3-sonnet")
        service = self._make_service(models=[model])
        # Should not raise
        await service.validate_model_for_chat(
            AsyncMock(), model_id="claude-3-sonnet", user_id="u1"
        )


# ============================================================================
# ChatService - update_session_name_if_untitled
# ============================================================================


class TestChatServiceUpdateSessionNameIfUntitled:
    def _make_service(self, session=None):
        from ii_agent.chat.application.chat_service import ChatService

        class FakeRepo:
            async def get_by_id(self, db, session_id):
                return session

        return ChatService(
            file_processor=SimpleNamespace(_config=_make_settings()),
            tool_service=SimpleNamespace(),
            llm_loop=SimpleNamespace(),
            message_history=SimpleNamespace(),
            message_service=SimpleNamespace(),
            session_repo=FakeRepo(),
            chat_run_service=SimpleNamespace(),
            llm_setting_service=SimpleNamespace(),
            credit_service=None,
            container=SimpleNamespace(),
        )

    @pytest.mark.asyncio
    async def test_does_not_update_when_session_missing(self):
        service = self._make_service(session=None)
        # Should silently return
        await service.update_session_name_if_untitled(
            AsyncMock(), session_id="s1", query="New name"
        )

    @pytest.mark.asyncio
    async def test_updates_when_name_is_untitled(self):
        session = SimpleNamespace(name="Untitled")
        service = self._make_service(session=session)

        db = AsyncMock()
        await service.update_session_name_if_untitled(db, session_id="s1", query="My new query")
        assert session.name == "My new query"

    @pytest.mark.asyncio
    async def test_does_not_update_when_name_is_not_untitled(self):
        session = SimpleNamespace(name="Existing Name")
        service = self._make_service(session=session)

        db = AsyncMock()
        await service.update_session_name_if_untitled(db, session_id="s1", query="Ignored")
        assert session.name == "Existing Name"


# ============================================================================
# ChatService - stop_conversation
# ============================================================================


class TestChatServiceStopConversation:
    def _make_service(self, session=None, running_task=None):
        from ii_agent.chat.application.chat_service import ChatService

        class FakeRepo:
            async def get_by_id(self, db, session_id):
                return session

        class FakeChatRunService:
            async def find_running_for_cancel(self, db, *, session_id):
                return running_task

        class FakeMsgHistoryRepo:
            async def get_last_by_session(self, db, session_id):
                return None

        msg_history = SimpleNamespace(
            _repo=FakeMsgHistoryRepo()
        )

        return ChatService(
            file_processor=SimpleNamespace(_config=_make_settings()),
            tool_service=SimpleNamespace(),
            llm_loop=SimpleNamespace(),
            message_history=msg_history,
            message_service=SimpleNamespace(),
            session_repo=FakeRepo(),
            chat_run_service=FakeChatRunService(),
            llm_setting_service=SimpleNamespace(),
            credit_service=None,
            container=SimpleNamespace(),
        )

    @pytest.mark.asyncio
    async def test_raises_when_session_missing(self):
        from ii_agent.sessions.exceptions import SessionNotFoundError

        service = self._make_service(session=None)
        with pytest.raises(SessionNotFoundError):
            await service.stop_conversation(AsyncMock(), session_id="s1")

    @pytest.mark.asyncio
    async def test_returns_none_when_no_last_message(self):
        import uuid

        session = SimpleNamespace(user_id="u1")
        service = self._make_service(session=session, running_task=None)

        real_session_id = str(uuid.uuid4())
        result = await service.stop_conversation(AsyncMock(), session_id=real_session_id)
        assert result is None
