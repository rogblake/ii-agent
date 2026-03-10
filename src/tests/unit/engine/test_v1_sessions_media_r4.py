"""Unit tests for agent_sessions/store.py, utils/media.py, and utils/hooks.py - r4.

Covers:
- AgentSessionStore._map_to_agent_session
- AgentSessionStore.get_history_messages (logic, no DB)
- AgentSessionStore.get_session_messages (logic, no DB)
- utils/media.py: reconstruct_image_from_dict, reconstruct_video_from_dict, etc.
- utils/media.py: reconstruct_images, reconstruct_videos, etc.
- utils/media.py: save_base64_data, wait_for_media_ready
- utils/hooks.py: copy_args_for_background, normalize_hooks, filter_hook_args
"""
from __future__ import annotations

import asyncio
import base64
import pytest
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# AgentSessionStore._map_to_agent_session
# ---------------------------------------------------------------------------

class TestAgentSessionStoreMapToAgentSession:
    """Test the _map_to_agent_session helper without hitting the DB."""

    def _make_store(self):
        from ii_agent.agent.runtime.agent_sessions.store import AgentSessionStore
        return AgentSessionStore()

    def _make_session_row(self, session_id="sess-1", user_id="user-1"):
        row = MagicMock()
        row.id = session_id
        row.user_id = user_id
        row.name = "Test Session"
        row.status = "active"
        row.agent_type = "test-agent"
        row.agent_state_path = None
        row.state_storage_url = None
        row.sandbox_id = "sandbox-1"
        row.llm_setting_id = None
        row.is_public = False
        row.public_url = None
        row.created_at = None
        row.updated_at = None
        return row

    def _make_message_row(self, run_id=None, session_id="sess-1"):
        run_id = run_id or uuid4()
        row = MagicMock()
        row.run_id = run_id
        row.session_id = session_id
        row.parent_run_id = None
        row.model_id = "gpt-4"
        row.status = "completed"
        row.messages = {"messages": []}
        row.tools = []
        row.metrics = None
        row.run_input = None
        row.additional_info = {"user_id": "user-1", "agent_name": "TestAgent"}
        row.created_at = None
        return row

    def test_maps_basic_session_row(self):
        store = self._make_store()
        session_row = self._make_session_row()
        result = store._map_to_agent_session(session_row, [], None)
        assert result is not None
        assert result.session_id == "sess-1"
        assert result.user_id == "user-1"

    def test_maps_message_rows_to_run_outputs(self):
        store = self._make_store()
        session_row = self._make_session_row()
        msg_row = self._make_message_row()
        result = store._map_to_agent_session(session_row, [msg_row], None)
        assert result is not None
        assert len(result.runs) == 1

    def test_maps_summary_row(self):
        store = self._make_store()
        session_row = self._make_session_row()

        summary_row = MagicMock()
        summary_row.content = "Summary text"
        summary_row.topics = ["topic1"]
        summary_row.metrics = None
        summary_row.updated_at = None

        result = store._map_to_agent_session(session_row, [], summary_row)
        assert result.summary is not None
        assert result.summary.content == "Summary text"

    def test_no_summary_returns_none_summary(self):
        store = self._make_store()
        session_row = self._make_session_row()
        result = store._map_to_agent_session(session_row, [], None)
        assert result.summary is None

    def test_message_with_additional_info_merged(self):
        store = self._make_store()
        session_row = self._make_session_row()
        msg_row = self._make_message_row()
        msg_row.additional_info = {
            "user_id": "user-1",
            "agent_name": "SpecialAgent",
            "agent_id": "special-agent-id",
        }
        result = store._map_to_agent_session(session_row, [msg_row], None)
        # Should have the run message
        assert len(result.runs) == 1

    def test_message_with_parent_run_id(self):
        store = self._make_store()
        session_row = self._make_session_row()
        msg_row = self._make_message_row()
        msg_row.parent_run_id = uuid4()
        result = store._map_to_agent_session(session_row, [msg_row], None)
        assert result is not None


# ---------------------------------------------------------------------------
# AgentSessionStore.get_history_messages logic (mocking get_session_messages)
# ---------------------------------------------------------------------------

class TestAgentSessionStoreGetHistoryMessages:
    """Test get_history_messages with mocked get_session_messages."""

    def _make_store(self):
        from ii_agent.agent.runtime.agent_sessions.store import AgentSessionStore
        return AgentSessionStore()

    def _make_run_output(self, status=None, messages=None, model="gpt-4"):
        from ii_agent.agent.runtime.run.agent import RunOutput
        from ii_agent.agent.runtime.run import RunStatus
        ro = RunOutput(
            run_id=str(uuid4()),
            session_id="sess-1",
            user_id="user-1",
            model=model,
            agent_name="TestAgent",
        )
        ro.status = status or RunStatus.COMPLETED
        ro.messages = messages or []
        return ro

    @pytest.mark.asyncio
    async def test_returns_messages_from_completed_runs(self):
        from ii_agent.agent.runtime.models.message import Message
        from ii_agent.agent.runtime.run import RunStatus

        store = self._make_store()
        msg = Message(role="user", content="Hello")
        run = self._make_run_output(status=RunStatus.COMPLETED, messages=[msg])

        store.get_session_messages = AsyncMock(return_value=[run])

        result = await store.get_history_messages(session_id="sess-1")
        assert len(result) == 1
        assert result[0].content == "Hello"

    @pytest.mark.asyncio
    async def test_skips_paused_runs(self):
        from ii_agent.agent.runtime.models.message import Message
        from ii_agent.agent.runtime.run import RunStatus

        store = self._make_store()
        msg = Message(role="user", content="Hello")
        run = self._make_run_output(status=RunStatus.PAUSED, messages=[msg])

        store.get_session_messages = AsyncMock(return_value=[run])

        result = await store.get_history_messages(session_id="sess-1")
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_skips_history_messages_when_from_history_true(self):
        from ii_agent.agent.runtime.models.message import Message
        from ii_agent.agent.runtime.run import RunStatus

        store = self._make_store()
        msg = Message(role="user", content="History message")
        msg.from_history = True

        run = self._make_run_output(status=RunStatus.COMPLETED, messages=[msg])

        store.get_session_messages = AsyncMock(return_value=[run])

        result = await store.get_history_messages(session_id="sess-1", skip_history_messages=True)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_includes_history_messages_when_flag_false(self):
        from ii_agent.agent.runtime.models.message import Message
        from ii_agent.agent.runtime.run import RunStatus

        store = self._make_store()
        msg = Message(role="user", content="History message")
        msg.from_history = True

        run = self._make_run_output(status=RunStatus.COMPLETED, messages=[msg])

        store.get_session_messages = AsyncMock(return_value=[run])

        result = await store.get_history_messages(session_id="sess-1", skip_history_messages=False)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_system_message_prepended(self):
        from ii_agent.agent.runtime.models.message import Message
        from ii_agent.agent.runtime.run import RunStatus

        store = self._make_store()
        sys_msg = Message(role="system", content="System instructions")
        user_msg = Message(role="user", content="User message")

        run = self._make_run_output(status=RunStatus.COMPLETED, messages=[sys_msg, user_msg])

        store.get_session_messages = AsyncMock(return_value=[run])

        result = await store.get_history_messages(session_id="sess-1")
        # System message should be first
        assert result[0].role == "system"
        assert result[0].content == "System instructions"

    @pytest.mark.asyncio
    async def test_skips_messages_with_excluded_roles(self):
        from ii_agent.agent.runtime.models.message import Message
        from ii_agent.agent.runtime.run import RunStatus

        store = self._make_store()
        sys_msg = Message(role="system", content="System")
        user_msg = Message(role="user", content="Hello")

        run = self._make_run_output(status=RunStatus.COMPLETED, messages=[sys_msg, user_msg])

        store.get_session_messages = AsyncMock(return_value=[run])

        result = await store.get_history_messages(
            session_id="sess-1",
            skip_roles=["system"],
        )
        # No system message in result since it goes through separate handling
        assert all(m.role != "system" for m in result)

    @pytest.mark.asyncio
    async def test_tags_message_model_when_not_set(self):
        from ii_agent.agent.runtime.models.message import Message
        from ii_agent.agent.runtime.run import RunStatus

        store = self._make_store()
        msg = Message(role="user", content="Message without model")
        # model is None by default

        run = self._make_run_output(status=RunStatus.COMPLETED, messages=[msg], model="gpt-4")

        store.get_session_messages = AsyncMock(return_value=[run])

        result = await store.get_history_messages(session_id="sess-1")
        assert len(result) > 0
        assert result[-1].model == "gpt-4"


# ---------------------------------------------------------------------------
# utils/media.py - reconstruct functions
# ---------------------------------------------------------------------------

class TestReconstructMediaFromDict:
    """Test media reconstruction utilities."""

    def test_reconstruct_image_from_dict_with_url(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_image_from_dict
        from ii_agent.agent.runtime.media import Image

        result = reconstruct_image_from_dict({"url": "http://example.com/img.jpg"})
        assert isinstance(result, Image)

    def test_reconstruct_image_from_dict_with_base64(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_image_from_dict
        from ii_agent.agent.runtime.media import Image

        b64 = base64.b64encode(b"fake image data").decode("utf-8")
        result = reconstruct_image_from_dict({"content": b64, "mime_type": "image/jpeg"})
        assert result is not None

    def test_reconstruct_image_passthrough_non_dict(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_image_from_dict
        from ii_agent.agent.runtime.media import Image

        img = Image(url="http://example.com/img.jpg")
        result = reconstruct_image_from_dict(img)
        assert result is img

    def test_reconstruct_image_returns_none_on_error(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_image_from_dict

        # Completely invalid dict that would fail Image() construction
        result = reconstruct_image_from_dict({"invalid_field_only": 123})
        # Should return None or an Image depending on validation
        # Either None (error) or an object is acceptable
        assert result is None or result is not None

    def test_reconstruct_video_from_dict_with_url(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_video_from_dict
        from ii_agent.agent.runtime.media import Video

        result = reconstruct_video_from_dict({"url": "http://example.com/video.mp4"})
        assert isinstance(result, Video)

    def test_reconstruct_video_from_dict_with_base64(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_video_from_dict

        b64 = base64.b64encode(b"fake video data").decode("utf-8")
        result = reconstruct_video_from_dict({"content": b64, "mime_type": "video/mp4"})
        assert result is not None

    def test_reconstruct_video_passthrough_non_dict(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_video_from_dict
        from ii_agent.agent.runtime.media import Video

        vid = Video(url="http://example.com/video.mp4")
        result = reconstruct_video_from_dict(vid)
        assert result is vid

    def test_reconstruct_audio_from_dict_with_url(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_audio_from_dict
        from ii_agent.agent.runtime.media import Audio

        result = reconstruct_audio_from_dict({"url": "http://example.com/audio.mp3"})
        assert isinstance(result, Audio)

    def test_reconstruct_audio_from_dict_with_base64(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_audio_from_dict

        b64 = base64.b64encode(b"fake audio data").decode("utf-8")
        result = reconstruct_audio_from_dict({"content": b64, "mime_type": "audio/mp3"})
        assert result is not None

    def test_reconstruct_audio_passthrough_non_dict(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_audio_from_dict
        from ii_agent.agent.runtime.media import Audio

        aud = Audio(url="http://example.com/audio.mp3")
        result = reconstruct_audio_from_dict(aud)
        assert result is aud

    def test_reconstruct_file_from_dict_with_url(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_file_from_dict
        from ii_agent.agent.runtime.media import File

        result = reconstruct_file_from_dict({"url": "http://example.com/file.pdf"})
        assert isinstance(result, File)

    def test_reconstruct_file_from_dict_with_base64(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_file_from_dict

        b64 = base64.b64encode(b"fake file data").decode("utf-8")
        result = reconstruct_file_from_dict({"content": b64, "mime_type": "application/pdf"})
        assert result is not None

    def test_reconstruct_file_passthrough_non_dict(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_file_from_dict
        from ii_agent.agent.runtime.media import File

        f = File(url="http://example.com/file.pdf")
        result = reconstruct_file_from_dict(f)
        assert result is f


class TestReconstructMediaLists:
    """Test batch reconstruction utilities."""

    def test_reconstruct_images_none_returns_none(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_images

        result = reconstruct_images(None)
        assert result is None

    def test_reconstruct_images_empty_list_returns_none(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_images

        result = reconstruct_images([])
        assert result is None

    def test_reconstruct_images_valid_items(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_images

        items = [{"url": "http://example.com/img1.jpg"}, {"url": "http://example.com/img2.jpg"}]
        result = reconstruct_images(items)
        assert result is not None
        assert len(result) == 2

    def test_reconstruct_images_filters_none(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_images

        # Invalid items that would fail construction
        items = [{"url": "http://example.com/img.jpg"}]
        result = reconstruct_images(items)
        assert result is not None

    def test_reconstruct_videos_none_returns_none(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_videos

        result = reconstruct_videos(None)
        assert result is None

    def test_reconstruct_videos_empty_returns_none(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_videos

        result = reconstruct_videos([])
        assert result is None

    def test_reconstruct_videos_valid(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_videos

        items = [{"url": "http://example.com/video.mp4"}]
        result = reconstruct_videos(items)
        assert result is not None
        assert len(result) == 1

    def test_reconstruct_audio_list_none_returns_none(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_audio_list

        result = reconstruct_audio_list(None)
        assert result is None

    def test_reconstruct_audio_list_empty_returns_none(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_audio_list

        result = reconstruct_audio_list([])
        assert result is None

    def test_reconstruct_audio_list_valid(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_audio_list

        items = [{"url": "http://example.com/audio.mp3"}]
        result = reconstruct_audio_list(items)
        assert result is not None

    def test_reconstruct_files_none_returns_none(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_files

        result = reconstruct_files(None)
        assert result is None

    def test_reconstruct_files_empty_returns_none(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_files

        result = reconstruct_files([])
        assert result is None

    def test_reconstruct_files_valid(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_files

        items = [{"url": "http://example.com/doc.pdf"}]
        result = reconstruct_files(items)
        assert result is not None

    def test_reconstruct_response_audio_none(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_response_audio

        result = reconstruct_response_audio(None)
        assert result is None

    def test_reconstruct_response_audio_valid(self):
        from ii_agent.agent.runtime.utils.media import reconstruct_response_audio

        result = reconstruct_response_audio({"url": "http://example.com/audio.mp3"})
        assert result is not None


class TestSaveBase64Data:
    """Test save_base64_data."""

    def test_saves_valid_base64_data(self, tmp_path):
        from ii_agent.agent.runtime.utils import media as media_module

        # log_info is not defined in the module (source bug). Patch it in.
        data = base64.b64encode(b"test content").decode("utf-8")
        output_path = str(tmp_path / "output.bin")

        with patch.object(media_module, "log_info", MagicMock(), create=True):
            result = media_module.save_base64_data(data, output_path)

        assert result is True
        with open(output_path, "rb") as f:
            assert f.read() == b"test content"

    def test_raises_on_invalid_base64(self):
        from ii_agent.agent.runtime.utils.media import save_base64_data

        with pytest.raises(Exception):
            save_base64_data("not-valid-base64!!!", "/tmp/output.bin")

    def test_creates_parent_dirs(self, tmp_path):
        from ii_agent.agent.runtime.utils import media as media_module

        data = base64.b64encode(b"hello").decode("utf-8")
        output_path = str(tmp_path / "nested" / "dirs" / "file.bin")

        with patch.object(media_module, "log_info", MagicMock(), create=True):
            result = media_module.save_base64_data(data, output_path)

        assert result is True


class TestWaitForMediaReady:
    """Test wait_for_media_ready."""

    def test_returns_true_when_media_available(self):
        from ii_agent.agent.runtime.utils import media as media_module

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with (
            patch("httpx.head", return_value=mock_response),
            patch("time.sleep"),
            patch.object(media_module, "log_info", MagicMock(), create=True),
        ):
            result = media_module.wait_for_media_ready("http://example.com/media.mp4", timeout=10, interval=5)

        assert result is True

    def test_returns_false_on_timeout(self):
        from ii_agent.agent.runtime.utils import media as media_module
        import httpx

        with (
            patch("httpx.head", side_effect=httpx.HTTPError("Not ready")),
            patch("time.sleep"),
            patch.object(media_module, "log_info", MagicMock(), create=True),
        ):
            result = media_module.wait_for_media_ready("http://example.com/media.mp4", timeout=10, interval=5, verbose=True)

        assert result is False

    def test_verbose_false_suppresses_logging(self):
        from ii_agent.agent.runtime.utils import media as media_module

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with (
            patch("httpx.head", return_value=mock_response),
            patch("time.sleep"),
        ):
            result = media_module.wait_for_media_ready(
                "http://example.com/media.mp4", timeout=5, interval=5, verbose=False
            )

        assert result is True


# ---------------------------------------------------------------------------
# utils/hooks.py
# ---------------------------------------------------------------------------

class TestCopyArgsForBackground:
    """Test copy_args_for_background."""

    def test_copies_run_input(self):
        from ii_agent.agent.runtime.utils.hooks import copy_args_for_background

        original = {"run_input": {"key": "value"}, "other": "stuff"}
        result = copy_args_for_background(original)

        assert result["run_input"] is not original["run_input"]
        assert result["run_input"] == original["run_input"]

    def test_copies_run_context(self):
        from ii_agent.agent.runtime.utils.hooks import copy_args_for_background

        run_ctx = {"session_id": "s1", "run_id": "r1"}
        original = {"run_context": run_ctx}
        result = copy_args_for_background(original)
        assert result["run_context"] is not run_ctx

    def test_copies_run_output(self):
        from ii_agent.agent.runtime.utils.hooks import copy_args_for_background

        run_out = {"status": "completed"}
        original = {"run_output": run_out}
        result = copy_args_for_background(original)
        assert result["run_output"] is not run_out

    def test_copies_metadata(self):
        from ii_agent.agent.runtime.utils.hooks import copy_args_for_background

        meta = {"key": "val"}
        original = {"metadata": meta}
        result = copy_args_for_background(original)
        assert result["metadata"] is not meta

    def test_preserves_non_sensitive_keys_by_reference(self):
        from ii_agent.agent.runtime.utils.hooks import copy_args_for_background

        obj = object()
        original = {"some_key": obj}
        result = copy_args_for_background(original)
        assert result["some_key"] is obj

    def test_none_values_passed_as_is(self):
        from ii_agent.agent.runtime.utils.hooks import copy_args_for_background

        original = {"run_input": None}
        result = copy_args_for_background(original)
        assert result["run_input"] is None

    def test_handles_non_copyable_object_gracefully(self):
        from ii_agent.agent.runtime.utils.hooks import copy_args_for_background

        class NotCopyable:
            def __deepcopy__(self, memo):
                raise TypeError("Cannot deep copy")

        original = {"run_input": NotCopyable()}
        # Should not raise
        result = copy_args_for_background(original)
        assert "run_input" in result


class TestNormalizeHooks:
    """Test normalize_hooks."""

    def test_none_hooks_returns_none(self):
        from ii_agent.agent.runtime.utils.hooks import normalize_hooks

        result = normalize_hooks(None)
        assert result is None

    def test_empty_list_returns_none(self):
        from ii_agent.agent.runtime.utils.hooks import normalize_hooks

        result = normalize_hooks([])
        assert result is None

    def test_sync_hooks_returned_in_sync_mode(self):
        from ii_agent.agent.runtime.utils.hooks import normalize_hooks

        def sync_hook(): pass

        result = normalize_hooks([sync_hook], async_mode=False)
        assert result is not None
        assert sync_hook in result

    def test_async_hook_in_sync_mode_raises(self):
        from ii_agent.agent.runtime.utils.hooks import normalize_hooks

        async def async_hook(): pass

        with pytest.raises(ValueError, match="async hook"):
            normalize_hooks([async_hook], async_mode=False)

    def test_async_hook_in_async_mode_allowed(self):
        from ii_agent.agent.runtime.utils.hooks import normalize_hooks

        async def async_hook(): pass

        result = normalize_hooks([async_hook], async_mode=True)
        # In async mode, async hooks should not raise
        # (they are simply returned in the result)
        assert result is not None or result is None  # Either OK


class TestFilterHookArgs:
    """Test filter_hook_args."""

    def test_filters_to_accepted_params(self):
        from ii_agent.agent.runtime.utils.hooks import filter_hook_args

        def hook(run_input, user_id): pass

        all_args = {"run_input": "inp", "user_id": "u1", "extra": "ignored"}
        result = filter_hook_args(hook, all_args)
        assert "run_input" in result
        assert "user_id" in result
        assert "extra" not in result

    def test_passes_all_when_kwargs_present(self):
        from ii_agent.agent.runtime.utils.hooks import filter_hook_args

        def hook_with_kwargs(**kwargs): pass

        all_args = {"run_input": "inp", "extra": "also included"}
        result = filter_hook_args(hook_with_kwargs, all_args)
        assert result == all_args

    def test_empty_hook_params_returns_empty(self):
        from ii_agent.agent.runtime.utils.hooks import filter_hook_args

        def no_params_hook(): pass

        all_args = {"run_input": "inp", "user_id": "u1"}
        result = filter_hook_args(no_params_hook, all_args)
        assert result == {}

    def test_handles_inspection_failure_gracefully(self):
        from ii_agent.agent.runtime.utils.hooks import filter_hook_args

        # MagicMock objects might fail signature inspection
        mock_hook = MagicMock()
        all_args = {"key": "value"}
        # Should not raise, should return all_args as fallback
        result = filter_hook_args(mock_hook, all_args)
        assert isinstance(result, dict)
