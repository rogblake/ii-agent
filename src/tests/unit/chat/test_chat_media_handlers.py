"""Unit tests for chat/media/handlers/*.

Covers:
- ImageMediaHandler.detect_mode() - mode detection logic
- ImageMediaHandler.build_tool_hint() - tool hint generation
- ImageMediaHandler.build_llm_context() - non-advanced mode returns []
- PromptBuilder static methods
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prefs(**kwargs):
    from ii_agent.chat.schemas import MediaPreferences

    defaults = dict(
        enabled=True,
        type="image",
        model_name="dall-e-3",
        provider=None,
        mini_tools=None,
        template_id=None,
        aspect_ratio=None,
        resolution=None,
        references=None,
        advanced_mode=False,
    )
    defaults.update(kwargs)
    return MediaPreferences(**defaults)


def _make_mini_tools(id_="tool-1", name="My Tool"):
    from ii_agent.chat.schemas import MiniTools

    return MiniTools(id=id_, name=name)


def _make_reference(file_id, ref_type):
    from ii_agent.chat.schemas import MediaReference

    return MediaReference(file_id=file_id, type=ref_type)


# ===========================================================================
# ImageMediaHandler – detect_mode
# ===========================================================================


class TestImageHandlerDetectMode:
    """Tests for ImageMediaHandler.detect_mode()."""

    def _handler(self):
        from ii_agent.chat.media.handlers.image_handler import ImageMediaHandler

        return ImageMediaHandler()

    def test_advanced_mode_flag_returns_advanced_strategy(self):
        from ii_agent.chat.media.modes.advanced_mode import AdvancedModeStrategy

        handler = self._handler()
        prefs = _make_prefs(advanced_mode=True)
        mode = handler.detect_mode(prefs)
        assert isinstance(mode, AdvancedModeStrategy)

    def test_mini_tools_returns_mini_tools_strategy(self):
        from ii_agent.chat.media.modes.mini_tools_mode import MiniToolsModeStrategy

        handler = self._handler()
        prefs = _make_prefs(mini_tools=_make_mini_tools())
        mode = handler.detect_mode(prefs)
        assert isinstance(mode, MiniToolsModeStrategy)

    def test_no_flags_returns_normal_mode(self):
        from ii_agent.chat.media.modes.normal_mode import NormalModeStrategy

        handler = self._handler()
        prefs = _make_prefs()
        mode = handler.detect_mode(prefs)
        assert isinstance(mode, NormalModeStrategy)

    def test_advanced_mode_takes_precedence_over_mini_tools(self):
        from ii_agent.chat.media.modes.advanced_mode import AdvancedModeStrategy

        handler = self._handler()
        prefs = _make_prefs(advanced_mode=True, mini_tools=_make_mini_tools())
        mode = handler.detect_mode(prefs)
        assert isinstance(mode, AdvancedModeStrategy)


# ===========================================================================
# ImageMediaHandler – build_llm_context
# ===========================================================================


class TestImageHandlerBuildLlmContext:
    """Tests for ImageMediaHandler.build_llm_context()."""

    def _handler(self):
        from ii_agent.chat.media.handlers.image_handler import ImageMediaHandler

        return ImageMediaHandler()

    async def test_normal_mode_returns_empty_list(self):
        from ii_agent.chat.media.modes.normal_mode import NormalModeStrategy

        handler = self._handler()
        prefs = _make_prefs()
        mode = NormalModeStrategy()

        result = await handler.build_llm_context(
            db_session=AsyncMock(),
            session_id="s1",
            mode_strategy=mode,
            media_preferences=prefs,
        )
        assert result == []

    async def test_mini_tools_mode_returns_empty_list(self):
        from ii_agent.chat.media.modes.mini_tools_mode import MiniToolsModeStrategy

        handler = self._handler()
        prefs = _make_prefs(mini_tools=_make_mini_tools())
        mode = MiniToolsModeStrategy()

        result = await handler.build_llm_context(
            db_session=AsyncMock(),
            session_id="s1",
            mode_strategy=mode,
            media_preferences=prefs,
        )
        assert result == []

    async def test_advanced_mode_no_references_still_processes(self):
        """Advanced mode with no references and no session images returns empty."""
        from ii_agent.chat.media.modes.advanced_mode import AdvancedModeStrategy
        from ii_agent.chat.media.utils.reference_resolver import ReferenceResolver

        handler = self._handler()
        prefs = _make_prefs(advanced_mode=True)
        mode = AdvancedModeStrategy()

        with patch.object(
            ReferenceResolver,
            "get_session_images",
            new=AsyncMock(return_value=[]),
        ):
            result = await handler.build_llm_context(
                db_session=AsyncMock(),
                session_id="s1",
                mode_strategy=mode,
                media_preferences=prefs,
            )

        # No references, no generated images -> empty list
        assert isinstance(result, list)
        assert len(result) == 0


# ===========================================================================
# ImageMediaHandler – build_tool_hint
# ===========================================================================


class TestImageHandlerBuildToolHint:
    """Tests for ImageMediaHandler.build_tool_hint()."""

    def _handler(self):
        from ii_agent.chat.media.handlers.image_handler import ImageMediaHandler

        return ImageMediaHandler()

    async def test_hint_contains_media_type(self):
        from ii_agent.chat.media.modes.normal_mode import NormalModeStrategy

        handler = self._handler()
        prefs = _make_prefs()
        mode = NormalModeStrategy()

        hint = await handler.build_tool_hint(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=prefs,
            mode_strategy=mode,
        )
        assert "image" in hint

    async def test_hint_contains_model_name(self):
        from ii_agent.chat.media.modes.normal_mode import NormalModeStrategy

        handler = self._handler()
        prefs = _make_prefs(model_name="dall-e-3")
        mode = NormalModeStrategy()

        hint = await handler.build_tool_hint(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=prefs,
            mode_strategy=mode,
        )
        assert "dall-e-3" in hint

    async def test_hint_contains_settings_constraint_when_aspect_ratio_set(self):
        from ii_agent.chat.media.modes.normal_mode import NormalModeStrategy

        handler = self._handler()
        prefs = _make_prefs(aspect_ratio="16:9")
        mode = NormalModeStrategy()

        hint = await handler.build_tool_hint(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=prefs,
            mode_strategy=mode,
        )
        assert "16:9" in hint

    async def test_hint_contains_mini_tool_fragment_when_mini_tools_set(self):
        from ii_agent.chat.media.modes.mini_tools_mode import MiniToolsModeStrategy

        handler = self._handler()
        prefs = _make_prefs(mini_tools=_make_mini_tools(id_="my-tool", name="My Tool"))
        mode = MiniToolsModeStrategy(clear_context=False)

        with patch(
            "ii_agent.chat.media.modes.mini_tools_mode.MediaTemplateService"
        ) as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.get_media_template_by_id = AsyncMock(return_value=None)
            mock_svc_cls.return_value = mock_svc

            hint = await handler.build_tool_hint(
                db_session=AsyncMock(),
                session_id="s1",
                media_preferences=prefs,
                mode_strategy=mode,
            )
        # mini_tools hint fragment contains the tool id
        assert "my-tool" in hint

    async def test_hint_instructs_to_call_generate_image(self):
        from ii_agent.chat.media.modes.normal_mode import NormalModeStrategy

        handler = self._handler()
        prefs = _make_prefs()
        mode = NormalModeStrategy()

        hint = await handler.build_tool_hint(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=prefs,
            mode_strategy=mode,
        )
        assert "generate_image" in hint


# ===========================================================================
# PromptBuilder static methods
# ===========================================================================


class TestPromptBuilder:
    """Tests for PromptBuilder helper methods."""

    def test_build_settings_constraint_empty_when_no_settings(self):
        from ii_agent.chat.media.utils.prompt_builder import PromptBuilder

        result = PromptBuilder.build_settings_constraint(
            aspect_ratio=None, resolution=None
        )
        assert result == ""

    def test_build_settings_constraint_includes_aspect_ratio(self):
        from ii_agent.chat.media.utils.prompt_builder import PromptBuilder

        result = PromptBuilder.build_settings_constraint(
            aspect_ratio="16:9", resolution=None
        )
        assert "16:9" in result

    def test_build_settings_constraint_includes_resolution(self):
        from ii_agent.chat.media.utils.prompt_builder import PromptBuilder

        result = PromptBuilder.build_settings_constraint(
            aspect_ratio=None, resolution="1024x1024"
        )
        assert "1024x1024" in result

    def test_build_settings_constraint_with_both(self):
        from ii_agent.chat.media.utils.prompt_builder import PromptBuilder

        result = PromptBuilder.build_settings_constraint(
            aspect_ratio="4:3", resolution="2048x2048"
        )
        assert "4:3" in result
        assert "2048x2048" in result

    def test_build_mini_tool_hint_includes_id_and_name(self):
        from ii_agent.chat.media.utils.prompt_builder import PromptBuilder

        result = PromptBuilder.build_mini_tool_hint(
            mini_tool_id="my-id", mini_tool_name="My Name"
        )
        assert "my-id" in result
        assert "My Name" in result

    def test_build_reference_guidance_empty_list(self):
        from ii_agent.chat.media.utils.prompt_builder import PromptBuilder

        guidance, index_map, next_idx = PromptBuilder.build_reference_guidance(
            references=[], starting_index=1
        )
        assert guidance == ""
        assert index_map == {}
        assert next_idx == 1

    def test_build_reference_guidance_subject_only(self):
        from ii_agent.chat.media.utils.prompt_builder import PromptBuilder

        refs = [_make_reference("f1", "subject")]
        guidance, index_map, next_idx = PromptBuilder.build_reference_guidance(refs)
        assert "SUBJECT" in guidance
        assert "subject" in index_map
        assert index_map["subject"] == [1]
        assert next_idx == 2

    def test_build_reference_guidance_scene_only(self):
        from ii_agent.chat.media.utils.prompt_builder import PromptBuilder

        refs = [_make_reference("f1", "scene")]
        guidance, index_map, next_idx = PromptBuilder.build_reference_guidance(refs)
        assert "SCENE" in guidance
        assert "scene" in index_map

    def test_build_reference_guidance_style_only(self):
        from ii_agent.chat.media.utils.prompt_builder import PromptBuilder

        refs = [_make_reference("f1", "style")]
        guidance, index_map, next_idx = PromptBuilder.build_reference_guidance(refs)
        assert "STYLE" in guidance
        assert "style" in index_map

    def test_build_reference_guidance_ordering_subject_scene_style(self):
        from ii_agent.chat.media.utils.prompt_builder import PromptBuilder

        refs = [
            _make_reference("f1", "subject"),
            _make_reference("f2", "scene"),
            _make_reference("f3", "style"),
        ]
        guidance, index_map, next_idx = PromptBuilder.build_reference_guidance(refs)
        # subject starts at index 1, scene at 2, style at 3 -> next is 4
        assert index_map["subject"] == [1]
        assert index_map["scene"] == [2]
        assert index_map["style"] == [3]
        assert next_idx == 4

    def test_build_reference_guidance_multiple_subjects(self):
        from ii_agent.chat.media.utils.prompt_builder import PromptBuilder

        refs = [
            _make_reference("f1", "subject"),
            _make_reference("f2", "subject"),
        ]
        guidance, index_map, next_idx = PromptBuilder.build_reference_guidance(refs)
        assert index_map["subject"] == [1, 2]
        assert next_idx == 3

    def test_build_previous_images_guidance_includes_index(self):
        from ii_agent.chat.media.utils.prompt_builder import PromptBuilder

        result = PromptBuilder.build_previous_images_guidance(starting_index=5)
        assert "#5" in result

    def test_build_checklist_empty_for_no_references(self):
        from ii_agent.chat.media.utils.prompt_builder import PromptBuilder

        result = PromptBuilder.build_checklist(references=[])
        assert result == ""

    def test_build_checklist_includes_subject_check(self):
        from ii_agent.chat.media.utils.prompt_builder import PromptBuilder

        refs = [_make_reference("f1", "subject")]
        result = PromptBuilder.build_checklist(references=refs)
        assert "Subject" in result or "subject" in result.lower()

    def test_build_checklist_includes_scene_check(self):
        from ii_agent.chat.media.utils.prompt_builder import PromptBuilder

        refs = [_make_reference("f1", "scene")]
        result = PromptBuilder.build_checklist(references=refs)
        assert "SCENE" in result or "scene" in result.lower()

    def test_build_checklist_includes_style_checks_when_style_ref(self):
        from ii_agent.chat.media.utils.prompt_builder import PromptBuilder

        refs = [_make_reference("f1", "style")]
        result = PromptBuilder.build_checklist(references=refs)
        assert "STYLE" in result or "style" in result.lower()
