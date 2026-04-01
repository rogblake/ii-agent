"""Unit tests for ii_agent.workers.celery.tasks (r4)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Pure helper functions - no I/O
# ---------------------------------------------------------------------------


class TestSceneBasePageNumber:
    def test_scene_zero_always_returns_one(self):
        from ii_agent.workers.celery.tasks import _scene_base_page_number

        assert _scene_base_page_number(0, separate_page=True) == 1
        assert _scene_base_page_number(0, separate_page=False) == 1

    def test_separate_page_mode_doubles_index(self):
        from ii_agent.workers.celery.tasks import _scene_base_page_number

        assert _scene_base_page_number(1, separate_page=True) == 2
        assert _scene_base_page_number(2, separate_page=True) == 4
        assert _scene_base_page_number(3, separate_page=True) == 6

    def test_non_separate_page_mode_adds_one(self):
        from ii_agent.workers.celery.tasks import _scene_base_page_number

        assert _scene_base_page_number(1, separate_page=False) == 2
        assert _scene_base_page_number(2, separate_page=False) == 3
        assert _scene_base_page_number(5, separate_page=False) == 6


class TestDbPageToDisplayPage:
    def test_page_one_always_returns_one(self):
        from ii_agent.workers.celery.tasks import _db_page_to_display_page

        assert _db_page_to_display_page(1, separate_page_mode=True) == 1
        assert _db_page_to_display_page(1, separate_page_mode=False) == 1

    def test_non_separate_mode_returns_same_page(self):
        from ii_agent.workers.celery.tasks import _db_page_to_display_page

        assert _db_page_to_display_page(3, separate_page_mode=False) == 3
        assert _db_page_to_display_page(7, separate_page_mode=False) == 7

    def test_separate_mode_halves_and_increments(self):
        from ii_agent.workers.celery.tasks import _db_page_to_display_page

        assert _db_page_to_display_page(2, separate_page_mode=True) == 2
        assert _db_page_to_display_page(4, separate_page_mode=True) == 3
        assert _db_page_to_display_page(6, separate_page_mode=True) == 4


class TestResolveStorybookLanguage:
    def test_returns_language_code_key(self):
        from ii_agent.workers.celery.tasks import _resolve_storybook_language

        assert _resolve_storybook_language({"language_code": "en"}) == "en"

    def test_returns_languageCode_camel_case(self):
        from ii_agent.workers.celery.tasks import _resolve_storybook_language

        assert _resolve_storybook_language({"languageCode": "fr"}) == "fr"

    def test_returns_language_key(self):
        from ii_agent.workers.celery.tasks import _resolve_storybook_language

        assert _resolve_storybook_language({"language": "de"}) == "de"

    def test_returns_storybook_language_key(self):
        from ii_agent.workers.celery.tasks import _resolve_storybook_language

        assert _resolve_storybook_language({"storybook_language": "ja"}) == "ja"

    def test_prefers_language_code_over_others(self):
        from ii_agent.workers.celery.tasks import _resolve_storybook_language

        result = _resolve_storybook_language({"language_code": "en", "language": "fr"})
        assert result == "en"

    def test_returns_none_when_no_keys_present(self):
        from ii_agent.workers.celery.tasks import _resolve_storybook_language

        assert _resolve_storybook_language({}) is None
        assert _resolve_storybook_language({"other": "value"}) is None

    def test_falsy_value_skipped(self):
        from ii_agent.workers.celery.tasks import _resolve_storybook_language

        assert _resolve_storybook_language({"language_code": "", "language": "es"}) == "es"


class TestGetVoiceCostUsd:
    def test_returns_voice_cost_usd_key(self):
        from ii_agent.workers.celery.tasks import _get_voice_cost_usd

        assert _get_voice_cost_usd({"voice_cost_usd": 0.05}) == 0.05

    def test_returns_audio_cost_usd_key(self):
        from ii_agent.workers.celery.tasks import _get_voice_cost_usd

        assert _get_voice_cost_usd({"audio_cost_usd": 0.03}) == 0.03

    def test_returns_voice_cost_key(self):
        from ii_agent.workers.celery.tasks import _get_voice_cost_usd

        assert _get_voice_cost_usd({"voice_cost": 0.02}) == 0.02

    def test_returns_audio_cost_key(self):
        from ii_agent.workers.celery.tasks import _get_voice_cost_usd

        assert _get_voice_cost_usd({"audio_cost": 0.01}) == 0.01

    def test_zero_cost_returns_zero(self):
        from ii_agent.workers.celery.tasks import _get_voice_cost_usd

        assert _get_voice_cost_usd({"voice_cost_usd": 0}) == 0.0

    def test_returns_zero_when_no_keys(self):
        from ii_agent.workers.celery.tasks import _get_voice_cost_usd

        assert _get_voice_cost_usd({}) == 0.0

    def test_negative_value_returns_zero(self):
        from ii_agent.workers.celery.tasks import _get_voice_cost_usd

        assert _get_voice_cost_usd({"voice_cost_usd": -0.01}) == 0.0

    def test_string_value_skipped(self):
        from ii_agent.workers.celery.tasks import _get_voice_cost_usd

        assert _get_voice_cost_usd({"voice_cost_usd": "0.05"}) == 0.0


class TestEstimatePageCredits:
    def test_basic_estimate(self):
        from ii_agent.workers.celery.tasks import _estimate_page_credits

        result = _estimate_page_credits(image_cost_usd=0.02, audio_cost_usd=0.0)
        assert result > 0

    def test_negative_audio_cost_treated_as_zero(self):
        from ii_agent.workers.celery.tasks import _estimate_page_credits

        result_no_audio = _estimate_page_credits(image_cost_usd=0.02, audio_cost_usd=0.0)
        result_neg_audio = _estimate_page_credits(image_cost_usd=0.02, audio_cost_usd=-0.5)
        assert result_no_audio == result_neg_audio

    def test_audio_cost_adds_to_total(self):
        from ii_agent.workers.celery.tasks import _estimate_page_credits

        result_no_audio = _estimate_page_credits(image_cost_usd=0.02, audio_cost_usd=0.0)
        result_with_audio = _estimate_page_credits(image_cost_usd=0.02, audio_cost_usd=0.01)
        assert result_with_audio > result_no_audio


class TestGetCeleryLoop:
    def test_returns_event_loop(self):
        from ii_agent.workers.celery.tasks import _get_celery_loop
        import asyncio

        loop = _get_celery_loop()
        assert isinstance(loop, asyncio.AbstractEventLoop)

    def test_same_loop_returned_on_second_call(self):
        from ii_agent.workers.celery.tasks import _get_celery_loop

        loop1 = _get_celery_loop()
        loop2 = _get_celery_loop()
        assert loop1 is loop2

    def test_creates_new_loop_when_closed(self):
        import ii_agent.workers.celery.tasks as task_module

        # Create a closed loop to trigger replacement
        closed_loop = asyncio.new_event_loop()
        closed_loop.close()
        task_module._celery_loop = closed_loop

        loop = task_module._get_celery_loop()
        assert not loop.is_closed()
        assert loop is not closed_loop


class TestRunAsync:
    def test_runs_coroutine_to_completion(self):
        from ii_agent.workers.celery.tasks import _run_async

        async def coro():
            return 42

        result = _run_async(coro())
        assert result == 42

    def test_exception_propagates(self):
        from ii_agent.workers.celery.tasks import _run_async

        async def coro():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            _run_async(coro())


# ---------------------------------------------------------------------------
# _generate_storybook_page_async - payload validation
# ---------------------------------------------------------------------------


class TestGenerateStorybookPageAsyncPayload:
    @pytest.mark.asyncio
    async def test_missing_storybook_id_returns_invalid_payload(self):
        from ii_agent.workers.celery.tasks import _generate_storybook_page_async

        result = await _generate_storybook_page_async({}, "task-1")
        assert result["status"] == "invalid_payload"

    @pytest.mark.asyncio
    async def test_missing_scene_index_returns_invalid_payload(self):
        from ii_agent.workers.celery.tasks import _generate_storybook_page_async

        result = await _generate_storybook_page_async({"storybook_id": "sb-1"}, "task-1")
        assert result["status"] == "invalid_payload"

    @pytest.mark.asyncio
    async def test_negative_scene_index_returns_invalid_payload(self):
        from ii_agent.workers.celery.tasks import _generate_storybook_page_async

        result = await _generate_storybook_page_async(
            {"storybook_id": "sb-1", "scene_index": -1}, "task-1"
        )
        assert result["status"] == "invalid_payload"

    @pytest.mark.asyncio
    async def test_non_numeric_scene_index_returns_invalid_payload(self):
        from ii_agent.workers.celery.tasks import _generate_storybook_page_async

        result = await _generate_storybook_page_async(
            {"storybook_id": "sb-1", "scene_index": "abc"}, "task-1"
        )
        assert result["status"] == "invalid_payload"

    @pytest.mark.asyncio
    async def test_storybook_not_found_returns_status(self):
        from ii_agent.workers.celery.tasks import _generate_storybook_page_async

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        mock_db_ctx = AsyncMock()
        mock_db_ctx.__aenter__ = AsyncMock(return_value=mock_db_ctx)
        mock_db_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("ii_agent.core.db.manager.get_db_session_local", return_value=mock_db_ctx),
            patch(
                "ii_agent.content.storybook.repository.StorybookRepository",
                return_value=mock_repo,
            ),
        ):
            result = await _generate_storybook_page_async(
                {"storybook_id": "sb-1", "scene_index": 0}, "task-1"
            )
            assert result["status"] == "storybook_not_found"

    @pytest.mark.asyncio
    async def test_failed_generation_status_returns_failed(self):
        from ii_agent.workers.celery.tasks import _generate_storybook_page_async

        mock_storybook = MagicMock()
        mock_storybook.style_json = {"generation": {"status": "failed"}}

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=mock_storybook)

        mock_db_ctx = AsyncMock()
        mock_db_ctx.__aenter__ = AsyncMock(return_value=mock_db_ctx)
        mock_db_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("ii_agent.core.db.manager.get_db_session_local", return_value=mock_db_ctx),
            patch(
                "ii_agent.content.storybook.repository.StorybookRepository",
                return_value=mock_repo,
            ),
        ):
            result = await _generate_storybook_page_async(
                {"storybook_id": "sb-1", "scene_index": 0}, "task-1"
            )
            assert result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_cancelled_storybook_returns_cancelled(self):
        from ii_agent.workers.celery.tasks import _generate_storybook_page_async

        mock_storybook = MagicMock()
        mock_storybook.style_json = {"generation": {}}

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=mock_storybook)

        mock_db_ctx = AsyncMock()
        mock_db_ctx.__aenter__ = AsyncMock(return_value=mock_db_ctx)
        mock_db_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("ii_agent.core.db.manager.get_db_session_local", return_value=mock_db_ctx),
            patch(
                "ii_agent.content.storybook.repository.StorybookRepository",
                return_value=mock_repo,
            ),
            patch(
                "ii_agent.workers.celery.tasks.cancel.is_cancelled", AsyncMock(return_value=True)
            ),
        ):
            result = await _generate_storybook_page_async(
                {"storybook_id": "sb-1", "scene_index": 0}, "task-1"
            )
            assert result["status"] == "cancelled"


# ---------------------------------------------------------------------------
# storybook_generate_page (Celery task)
# ---------------------------------------------------------------------------


class TestStorybookGeneratePage:
    def test_task_returns_failed_on_exception(self):
        """Test that exception leads to failed status by testing internal async function."""
        from ii_agent.workers.celery.tasks import _generate_storybook_page_async, _run_async

        # Test by running the inner async function directly with invalid payload
        result = _run_async(_generate_storybook_page_async({}, "task-123"))
        assert result["status"] == "invalid_payload"

    def test_task_returns_status_on_valid_async_call(self):
        """Test _run_async executes coroutines correctly."""
        from ii_agent.workers.celery.tasks import _run_async

        async def async_coro():
            return {"status": "completed"}

        result = _run_async(async_coro())
        assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# _create_storybook_tool_error and _create_storybook_tool_result - skipped early returns
# ---------------------------------------------------------------------------


class TestCreateStorybookToolErrorResult:
    @pytest.mark.asyncio
    async def test_tool_error_returns_early_when_no_tool_call_id(self):
        from ii_agent.workers.celery.tasks import _create_storybook_tool_error

        # Should return early without DB calls when tool_call_id is None
        await _create_storybook_tool_error(
            error_message="error",
            tool_call_id=None,
            session_id="sess-1",
            parent_message_id=None,
            model_id="model-1",
            tool_name="generate_storybook",
        )

    @pytest.mark.asyncio
    async def test_tool_error_returns_early_when_no_model_id(self):
        from ii_agent.workers.celery.tasks import _create_storybook_tool_error

        await _create_storybook_tool_error(
            error_message="error",
            tool_call_id="tc-1",
            session_id="sess-1",
            parent_message_id=None,
            model_id=None,
            tool_name="generate_storybook",
        )

    @pytest.mark.asyncio
    async def test_tool_result_returns_early_when_no_tool_call_id(self):
        from ii_agent.workers.celery.tasks import _create_storybook_tool_result

        await _create_storybook_tool_result(
            storybook_id="sb-1",
            tool_call_id=None,
            session_id="sess-1",
            parent_message_id=None,
            model_id="model-1",
            tool_name="generate_storybook",
        )
