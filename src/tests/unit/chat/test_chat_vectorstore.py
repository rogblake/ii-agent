"""Unit tests for chat/vectorstore/openai.py - OpenAIVectorStore."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from ii_agent.chat.vectorstore.openai import OpenAIVectorStore


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def _make_vector_store_record(
    user_id: str = "user-1",
    vector_store_id: str = "vs_abc",
    expires_at: datetime | None = None,
    provider: str = "openai",
) -> MagicMock:
    record = MagicMock()
    record.id = str(uuid.uuid4())
    record.user_id = user_id
    record.vector_store_id = vector_store_id
    record.provider = provider
    record.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
    record.updated_at = datetime.now(timezone.utc)
    record.expires_at = expires_at or (datetime.now(timezone.utc) + timedelta(days=7))
    record.raw_vector_object = {}
    return record


def _make_openai_vs_store() -> OpenAIVectorStore:
    """Create an OpenAIVectorStore with mocked internals."""
    with (
        patch("ii_agent.chat.vectorstore.openai.get_system_llm_config") as mock_cfg,
        patch("ii_agent.chat.vectorstore.openai.get_settings"),
        patch("ii_agent.chat.vectorstore.openai.AsyncOpenAI") as mock_openai,
    ):
        llm_cfg = MagicMock()
        llm_cfg.api_key.get_secret_value.return_value = "sk-test"
        llm_cfg.base_url = None
        llm_cfg.model = "gpt-4"
        mock_cfg.return_value = llm_cfg

        store = OpenAIVectorStore()
        store.client = MagicMock()
    return store


# ---------------------------------------------------------------------------
# _is_vector_store_expired
# ---------------------------------------------------------------------------

class TestIsVectorStoreExpired:
    @pytest.mark.asyncio
    async def test_not_expired_when_far_future(self):
        store = _make_openai_vs_store()
        record = _make_vector_store_record(
            expires_at=datetime.now(timezone.utc) + timedelta(days=10)
        )
        result = await store._is_vector_store_expired(record)
        assert result is False

    @pytest.mark.asyncio
    async def test_expired_when_within_buffer(self):
        store = _make_openai_vs_store()
        # Expiry is within 10-minute buffer
        record = _make_vector_store_record(
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)
        )
        result = await store._is_vector_store_expired(record)
        assert result is True

    @pytest.mark.asyncio
    async def test_not_expired_when_no_expiry(self):
        store = _make_openai_vs_store()
        record = _make_vector_store_record()
        record.expires_at = None
        result = await store._is_vector_store_expired(record)
        assert result is False

    @pytest.mark.asyncio
    async def test_expired_exactly_at_buffer(self):
        store = _make_openai_vs_store()
        record = _make_vector_store_record(
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=store.BUFFER_EXPIRY_MINUTES)
        )
        result = await store._is_vector_store_expired(record)
        assert result is True


# ---------------------------------------------------------------------------
# _check_vector_store_expired_on_provider
# ---------------------------------------------------------------------------

class TestCheckVectorStoreExpiredOnProvider:
    @pytest.mark.asyncio
    async def test_returns_true_if_status_expired(self):
        store = _make_openai_vs_store()
        provider_vs = MagicMock()
        provider_vs.status = "expired"
        provider_vs.expires_at = None
        store.client.vector_stores.retrieve = AsyncMock(return_value=provider_vs)

        result = await store._check_vector_store_expired_on_provider("vs_abc")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_if_about_to_expire(self):
        store = _make_openai_vs_store()
        provider_vs = MagicMock()
        provider_vs.status = "active"
        # Unix timestamp within buffer
        soon = datetime.now(timezone.utc) + timedelta(minutes=5)
        provider_vs.expires_at = int(soon.timestamp())
        store.client.vector_stores.retrieve = AsyncMock(return_value=provider_vs)

        result = await store._check_vector_store_expired_on_provider("vs_abc")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_if_far_from_expiry(self):
        store = _make_openai_vs_store()
        provider_vs = MagicMock()
        provider_vs.status = "active"
        future = datetime.now(timezone.utc) + timedelta(days=5)
        provider_vs.expires_at = int(future.timestamp())
        store.client.vector_stores.retrieve = AsyncMock(return_value=provider_vs)

        result = await store._check_vector_store_expired_on_provider("vs_abc")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_on_exception(self):
        store = _make_openai_vs_store()
        store.client.vector_stores.retrieve = AsyncMock(side_effect=Exception("not found"))

        result = await store._check_vector_store_expired_on_provider("vs_gone")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_expiry_date(self):
        store = _make_openai_vs_store()
        provider_vs = MagicMock()
        provider_vs.status = "active"
        provider_vs.expires_at = None
        store.client.vector_stores.retrieve = AsyncMock(return_value=provider_vs)

        result = await store._check_vector_store_expired_on_provider("vs_abc")
        assert result is False


# ---------------------------------------------------------------------------
# _create_vector_store_on_provider
# ---------------------------------------------------------------------------

class TestCreateVectorStoreOnProvider:
    @pytest.mark.asyncio
    async def test_creates_vector_store(self):
        store = _make_openai_vs_store()
        new_vs = MagicMock()
        new_vs.id = "vs_new"
        store.client.vector_stores.create = AsyncMock(return_value=new_vs)

        result = await store._create_vector_store_on_provider("user-1")
        assert result.id == "vs_new"
        store.client.vector_stores.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_provider_error(self):
        store = _make_openai_vs_store()
        store.client.vector_stores.create = AsyncMock(side_effect=Exception("quota exceeded"))

        with pytest.raises(Exception, match="quota exceeded"):
            await store._create_vector_store_on_provider("user-1")


# ---------------------------------------------------------------------------
# _get_vector_store_from_db
# ---------------------------------------------------------------------------

class TestGetVectorStoreFromDb:
    @pytest.mark.asyncio
    async def test_returns_record_when_found(self):
        store = _make_openai_vs_store()
        record = _make_vector_store_record()

        db_session = AsyncMock()
        scalar = MagicMock()
        scalar.scalar_one_or_none.return_value = record
        db_session.execute = AsyncMock(return_value=scalar)

        result = await store._get_vector_store_from_db(db_session, "user-1")
        assert result == record

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        store = _make_openai_vs_store()

        db_session = AsyncMock()
        scalar = MagicMock()
        scalar.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=scalar)

        result = await store._get_vector_store_from_db(db_session, "user-99")
        assert result is None


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

class TestDelete:
    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self):
        store = _make_openai_vs_store()
        db_session = AsyncMock()
        scalar = MagicMock()
        scalar.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=scalar)

        result = await store.delete(db_session, "user-1", "sess-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_deletes_from_provider_and_db(self):
        store = _make_openai_vs_store()
        record = _make_vector_store_record()

        db_session = AsyncMock()
        scalar = MagicMock()
        scalar.scalar_one_or_none.return_value = record
        db_session.execute = AsyncMock(return_value=scalar)
        db_session.delete = AsyncMock()
        db_session.commit = AsyncMock()

        store.client.vector_stores.delete = AsyncMock()

        result = await store.delete(db_session, "user-1", "sess-1")
        assert result is True
        store.client.vector_stores.delete.assert_called_once_with(record.vector_store_id)
        db_session.delete.assert_called_once_with(record)

    @pytest.mark.asyncio
    async def test_continues_if_provider_delete_fails(self):
        store = _make_openai_vs_store()
        record = _make_vector_store_record()

        db_session = AsyncMock()
        scalar = MagicMock()
        scalar.scalar_one_or_none.return_value = record
        db_session.execute = AsyncMock(return_value=scalar)
        db_session.delete = AsyncMock()
        db_session.commit = AsyncMock()

        store.client.vector_stores.delete = AsyncMock(side_effect=Exception("not found on provider"))

        result = await store.delete(db_session, "user-1", "sess-1")
        # Should still succeed and delete from DB
        assert result is True
        db_session.delete.assert_called_once_with(record)


# ---------------------------------------------------------------------------
# add_file
# ---------------------------------------------------------------------------

class TestAddFile:
    @pytest.mark.asyncio
    async def test_returns_zero_when_file_not_found_in_db(self):
        store = _make_openai_vs_store()
        record = _make_vector_store_record()

        @asynccontextmanager
        async def fake_db_cm():
            db = AsyncMock()
            scalar1 = MagicMock()
            scalar1.scalar_one_or_none.return_value = record  # vector store
            scalar2 = MagicMock()
            scalar2.scalar_one_or_none.return_value = None  # file not found
            db.execute = AsyncMock(side_effect=[scalar1, scalar2])
            db.commit = AsyncMock()
            yield db

        with patch("ii_agent.chat.vectorstore.openai.get_db_session_local", return_value=fake_db_cm()):
            with patch.object(store, "_get_or_create_vector_store", new=AsyncMock(return_value=record)):
                result = await store.add_file("user-1", "sess-1", "file-1")
        assert result == 0

    @pytest.mark.asyncio
    async def test_returns_one_on_success(self):
        store = _make_openai_vs_store()
        record = _make_vector_store_record()

        file_upload = MagicMock()
        file_upload.file_name = "test.pdf"
        file_upload.storage_path = "path/to/test.pdf"

        openai_file = MagicMock()
        openai_file.id = "file_abc"

        vs_file = MagicMock()
        vs_file.id = "vsf_abc"

        @asynccontextmanager
        async def fake_db_cm():
            db = AsyncMock()
            scalar1 = MagicMock()
            scalar1.scalar_one_or_none.return_value = file_upload
            db.execute = AsyncMock(return_value=scalar1)
            db.commit = AsyncMock()
            yield db

        store.client.files.create = AsyncMock(return_value=openai_file)
        store.client.vector_stores.files.create_and_poll = AsyncMock(return_value=vs_file)

        with patch("ii_agent.chat.vectorstore.openai.get_db_session_local", return_value=fake_db_cm()):
            with patch.object(store, "_get_or_create_vector_store", new=AsyncMock(return_value=record)):
                with patch("ii_agent.chat.vectorstore.openai.anyio.to_thread.run_sync", new=AsyncMock(return_value=b"pdf content")):
                    result = await store.add_file("user-1", "sess-1", "file-1")

        assert result == 1

    @pytest.mark.asyncio
    async def test_returns_zero_on_exception(self):
        store = _make_openai_vs_store()

        @asynccontextmanager
        async def fake_db_cm():
            db = AsyncMock()
            db.execute = AsyncMock(side_effect=Exception("DB error"))
            yield db

        with patch("ii_agent.chat.vectorstore.openai.get_db_session_local", return_value=fake_db_cm()):
            result = await store.add_file("user-1", "sess-1", "file-1")

        assert result == 0


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

class TestSearch:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        store = _make_openai_vs_store()
        record = _make_vector_store_record()

        content_part = MagicMock()
        content_part.text = "Found content"
        content_part.annotations = []

        output_item = MagicMock()
        output_item.content = [content_part]

        mock_response = MagicMock()
        mock_response.output = [output_item]

        store.client.responses.create = AsyncMock(return_value=mock_response)

        @asynccontextmanager
        async def fake_db_cm():
            db = AsyncMock()
            yield db

        with patch("ii_agent.chat.vectorstore.openai.get_db_session_local", return_value=fake_db_cm()):
            with patch.object(store, "_get_or_create_vector_store", new=AsyncMock(return_value=record)):
                results = await store.search("user-1", "sess-1", "my query")

        assert len(results) == 1
        assert results[0]["content"] == "Found content"

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_exception(self):
        store = _make_openai_vs_store()

        @asynccontextmanager
        async def fake_db_cm():
            db = AsyncMock()
            yield db

        with patch("ii_agent.chat.vectorstore.openai.get_db_session_local", return_value=fake_db_cm()):
            with patch.object(store, "_get_or_create_vector_store", new=AsyncMock(side_effect=Exception("error"))):
                results = await store.search("user-1", "sess-1", "query")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_extracts_citations(self):
        store = _make_openai_vs_store()
        record = _make_vector_store_record()

        annotation = MagicMock()
        fc = MagicMock()
        fc.file_id = "file_ref_1"
        fc.quote = "some quote"
        annotation.file_citation = fc

        content_part = MagicMock()
        content_part.text = "text with citation"
        content_part.annotations = [annotation]

        output_item = MagicMock()
        output_item.content = [content_part]

        mock_response = MagicMock()
        mock_response.output = [output_item]

        store.client.responses.create = AsyncMock(return_value=mock_response)

        @asynccontextmanager
        async def fake_db_cm():
            db = AsyncMock()
            yield db

        with patch("ii_agent.chat.vectorstore.openai.get_db_session_local", return_value=fake_db_cm()):
            with patch.object(store, "_get_or_create_vector_store", new=AsyncMock(return_value=record)):
                results = await store.search("user-1", "sess-1", "query")

        assert "citations" in results[0]["metadata"]


# ---------------------------------------------------------------------------
# add_files_batch
# ---------------------------------------------------------------------------

class TestAddFilesBatch:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_files_found(self):
        store = _make_openai_vs_store()
        record = _make_vector_store_record()

        @asynccontextmanager
        async def fake_db_cm():
            db = AsyncMock()
            scalar = MagicMock()
            scalar.scalars.return_value.all.return_value = []
            db.execute = AsyncMock(return_value=scalar)
            yield db

        with patch("ii_agent.chat.vectorstore.openai.get_db_session_local", return_value=fake_db_cm()):
            with patch.object(store, "_get_or_create_vector_store", new=AsyncMock(return_value=record)):
                result = await store.add_files_batch("user-1", "sess-1", ["file-1"])

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_exception(self):
        store = _make_openai_vs_store()

        @asynccontextmanager
        async def fake_db_cm():
            db = AsyncMock()
            db.execute = AsyncMock(side_effect=Exception("DB error"))
            yield db

        with patch("ii_agent.chat.vectorstore.openai.get_db_session_local", return_value=fake_db_cm()):
            result = await store.add_files_batch("user-1", "sess-1", ["file-1"])

        assert result == []

    @pytest.mark.asyncio
    async def test_skips_files_with_unsupported_mime_type(self):
        store = _make_openai_vs_store()
        record = _make_vector_store_record()

        file_upload = MagicMock()
        file_upload.file_name = "video.mp4"
        file_upload.storage_path = "path/to/video.mp4"

        @asynccontextmanager
        async def fake_db_cm():
            db = AsyncMock()
            scalar = MagicMock()
            scalar.scalars.return_value.all.return_value = [file_upload]
            db.execute = AsyncMock(return_value=scalar)
            yield db

        with patch("ii_agent.chat.vectorstore.openai.get_db_session_local", return_value=fake_db_cm()):
            with patch.object(store, "_get_or_create_vector_store", new=AsyncMock(return_value=record)):
                with patch("ii_agent.chat.vectorstore.openai.mimetypes.guess_type", return_value=("video/mp4", None)):
                    result = await store.add_files_batch("user-1", "sess-1", ["file-1"])

        assert result == []
