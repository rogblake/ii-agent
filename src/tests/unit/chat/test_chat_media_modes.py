"""Unit tests for chat/media/modes/*.

Covers:
- NormalModeStrategy
- AdvancedModeStrategy
- MiniToolsModeStrategy
- StorybookModeStrategy
- TemplateReferenceModeStrategy
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prefs(**kwargs):
    from ii_agent.chat.types import MediaPreferences

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


def _make_mini_tools(id_="t1", name="Tool One"):
    from ii_agent.chat.types import MiniTools

    return MiniTools(id=id_, name=name)


def _make_reference(file_id, ref_type):
    from ii_agent.chat.types import MediaReference

    return MediaReference(file_id=file_id, type=ref_type)


# ===========================================================================
# NormalModeStrategy
# ===========================================================================


class TestNormalModeStrategy:
    def test_should_clear_context_returns_false(self):
        from ii_agent.chat.media.modes.normal_mode import NormalModeStrategy

        mode = NormalModeStrategy()
        assert mode.should_clear_context() is False

    def test_get_mode_name_returns_normal(self):
        from ii_agent.chat.media.modes.normal_mode import NormalModeStrategy

        mode = NormalModeStrategy()
        assert mode.get_mode_name() == "normal"

    async def test_build_prompt_context_returns_empty_string(self):
        from ii_agent.chat.media.modes.normal_mode import NormalModeStrategy

        mode = NormalModeStrategy()
        result = await mode.build_prompt_context(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=_make_prefs(),
        )
        assert result == ""


# ===========================================================================
# AdvancedModeStrategy
# ===========================================================================


class TestAdvancedModeStrategy:
    def test_should_clear_context_returns_false(self):
        from ii_agent.chat.media.modes.advanced_mode import AdvancedModeStrategy

        mode = AdvancedModeStrategy()
        assert mode.should_clear_context() is False

    def test_get_mode_name_returns_advanced(self):
        from ii_agent.chat.media.modes.advanced_mode import AdvancedModeStrategy

        mode = AdvancedModeStrategy()
        assert mode.get_mode_name() == "advanced"

    async def test_build_prompt_context_no_references_includes_general_guidance(self):
        from ii_agent.chat.media.modes.advanced_mode import AdvancedModeStrategy

        mode = AdvancedModeStrategy()
        prefs = _make_prefs(references=None)

        result = await mode.build_prompt_context(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=prefs,
        )
        # Should include the no-references guidance
        assert "ADVANCED MODE" in result
        assert "PREVIOUSLY GENERATED" in result

    async def test_build_prompt_context_with_references_includes_reference_guidance(self):
        from ii_agent.chat.media.modes.advanced_mode import AdvancedModeStrategy

        mode = AdvancedModeStrategy()
        refs = [_make_reference("f1", "subject")]
        prefs = _make_prefs(references=refs)

        result = await mode.build_prompt_context(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=prefs,
        )
        assert "REFERENCE" in result
        assert "SUBJECT" in result

    async def test_build_prompt_context_with_all_reference_types(self):
        from ii_agent.chat.media.modes.advanced_mode import AdvancedModeStrategy

        mode = AdvancedModeStrategy()
        refs = [
            _make_reference("f1", "subject"),
            _make_reference("f2", "scene"),
            _make_reference("f3", "style"),
        ]
        prefs = _make_prefs(references=refs)

        result = await mode.build_prompt_context(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=prefs,
        )
        assert "SUBJECT" in result
        assert "SCENE" in result
        assert "STYLE" in result

    async def test_build_prompt_context_includes_previously_generated_guidance(self):
        from ii_agent.chat.media.modes.advanced_mode import AdvancedModeStrategy

        mode = AdvancedModeStrategy()
        refs = [_make_reference("f1", "subject")]
        prefs = _make_prefs(references=refs)

        result = await mode.build_prompt_context(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=prefs,
        )
        assert "PREVIOUSLY GENERATED" in result

    async def test_build_prompt_context_returns_nonempty_string(self):
        from ii_agent.chat.media.modes.advanced_mode import AdvancedModeStrategy

        mode = AdvancedModeStrategy()
        prefs = _make_prefs()
        result = await mode.build_prompt_context(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=prefs,
        )
        assert isinstance(result, str)
        assert len(result) > 0


# ===========================================================================
# MiniToolsModeStrategy
# ===========================================================================


class TestMiniToolsModeStrategy:
    def test_clear_context_defaults_to_true(self):
        from ii_agent.chat.media.modes.mini_tools_mode import MiniToolsModeStrategy

        mode = MiniToolsModeStrategy()
        assert mode.should_clear_context() is True

    def test_clear_context_can_be_disabled(self):
        from ii_agent.chat.media.modes.mini_tools_mode import MiniToolsModeStrategy

        mode = MiniToolsModeStrategy(clear_context=False)
        assert mode.should_clear_context() is False

    def test_get_mode_name_returns_mini_tools(self):
        from ii_agent.chat.media.modes.mini_tools_mode import MiniToolsModeStrategy

        mode = MiniToolsModeStrategy()
        assert mode.get_mode_name() == "mini_tools"

    async def test_build_prompt_context_no_mini_tools_returns_empty(self):
        from ii_agent.chat.media.modes.mini_tools_mode import MiniToolsModeStrategy

        mode = MiniToolsModeStrategy()
        prefs = _make_prefs()

        result = await mode.build_prompt_context(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=prefs,
        )
        assert result == ""

    async def test_build_prompt_context_with_mini_tools_and_no_template(self):
        """When template is not found, tool_fragment is empty and result is empty string."""
        from ii_agent.chat.media.modes.mini_tools_mode import MiniToolsModeStrategy

        mode = MiniToolsModeStrategy()
        prefs = _make_prefs(mini_tools=_make_mini_tools(id_="tool-1", name="T1"))

        with patch(
            "ii_agent.chat.media.modes.mini_tools_mode.MediaTemplateService"
        ) as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.get_media_template_by_id = AsyncMock(return_value=None)
            mock_svc_cls.return_value = mock_svc

            result = await mode.build_prompt_context(
                db_session=AsyncMock(),
                session_id="s1",
                media_preferences=prefs,
            )
        # Template not found -> tool_fragment = "", template_prompt_instruction = ""
        assert result == ""

    async def test_build_prompt_context_with_template_prompt(self):
        from ii_agent.chat.media.modes.mini_tools_mode import MiniToolsModeStrategy

        mode = MiniToolsModeStrategy()
        prefs = _make_prefs(mini_tools=_make_mini_tools(id_="t1", name="T1"))

        mock_template = SimpleNamespace(name="T1", prompt="Use bold colors", preview=None)

        with patch(
            "ii_agent.chat.media.modes.mini_tools_mode.MediaTemplateService"
        ) as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.get_media_template_by_id = AsyncMock(return_value=mock_template)
            mock_svc_cls.return_value = mock_svc

            result = await mode.build_prompt_context(
                db_session=AsyncMock(),
                session_id="s1",
                media_preferences=prefs,
            )
        assert "Use bold colors" in result

    async def test_build_prompt_context_handles_exception_gracefully(self):
        from ii_agent.chat.media.modes.mini_tools_mode import MiniToolsModeStrategy

        mode = MiniToolsModeStrategy()
        prefs = _make_prefs(mini_tools=_make_mini_tools(id_="t1", name="T1"))

        with patch(
            "ii_agent.chat.media.modes.mini_tools_mode.MediaTemplateService"
        ) as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.get_media_template_by_id = AsyncMock(side_effect=Exception("DB error"))
            mock_svc_cls.return_value = mock_svc

            # Should not raise even on exception
            result = await mode.build_prompt_context(
                db_session=AsyncMock(),
                session_id="s1",
                media_preferences=prefs,
            )
        assert isinstance(result, str)

    async def test_build_prompt_context_with_template_id_only(self):
        """Template ID without mini_tools also triggers template lookup."""
        from ii_agent.chat.media.modes.mini_tools_mode import MiniToolsModeStrategy

        mode = MiniToolsModeStrategy()
        prefs = _make_prefs(template_id="tmpl-123")

        mock_template = SimpleNamespace(name="My Template", prompt="Prompt text", preview=None)

        with patch(
            "ii_agent.chat.media.modes.mini_tools_mode.MediaTemplateService"
        ) as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.get_media_template_by_id = AsyncMock(return_value=mock_template)
            mock_svc_cls.return_value = mock_svc

            result = await mode.build_prompt_context(
                db_session=AsyncMock(),
                session_id="s1",
                media_preferences=prefs,
            )
        assert "tmpl-123" in result or "My Template" in result


# ===========================================================================
# StorybookModeStrategy
# ===========================================================================


class TestStorybookModeStrategy:
    def test_should_clear_context_returns_false(self):
        from ii_agent.chat.media.modes.storybook_mode import StorybookModeStrategy

        mode = StorybookModeStrategy()
        assert mode.should_clear_context() is False

    def test_get_mode_name_returns_storybook(self):
        from ii_agent.chat.media.modes.storybook_mode import StorybookModeStrategy

        mode = StorybookModeStrategy()
        assert mode.get_mode_name() == "storybook"

    async def test_build_prompt_context_returns_storybook_guidance(self):
        from ii_agent.chat.media.modes.storybook_mode import StorybookModeStrategy

        mode = StorybookModeStrategy()
        prefs = _make_prefs(type="storybook")

        result = await mode.build_prompt_context(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=prefs,
        )
        assert "STORYBOOK" in result

    async def test_build_prompt_context_includes_page_count_when_set(self):
        from ii_agent.chat.media.modes.storybook_mode import StorybookModeStrategy
        from ii_agent.chat.types import MediaPreferences

        mode = StorybookModeStrategy()
        prefs = MediaPreferences(
            enabled=True,
            type="storybook",
            model_name="model",
            page_count=5,
        )

        result = await mode.build_prompt_context(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=prefs,
        )
        assert "5" in result

    async def test_build_prompt_context_includes_language_instruction_when_set(self):
        from ii_agent.chat.media.modes.storybook_mode import StorybookModeStrategy
        from ii_agent.chat.types import MediaPreferences

        mode = StorybookModeStrategy()
        prefs = MediaPreferences(
            enabled=True,
            type="storybook",
            model_name="model",
            language="Vietnamese",
        )

        result = await mode.build_prompt_context(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=prefs,
        )
        assert "Vietnamese" in result

    async def test_build_prompt_context_includes_text_position_when_not_none(self):
        from ii_agent.chat.media.modes.storybook_mode import StorybookModeStrategy
        from ii_agent.chat.types import MediaPreferences

        mode = StorybookModeStrategy()
        prefs = MediaPreferences(
            enabled=True,
            type="storybook",
            model_name="model",
            text_position="left",
        )

        result = await mode.build_prompt_context(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=prefs,
        )
        assert "left" in result

    async def test_build_prompt_context_no_text_position_when_none_value(self):
        from ii_agent.chat.media.modes.storybook_mode import StorybookModeStrategy
        from ii_agent.chat.types import MediaPreferences

        mode = StorybookModeStrategy()
        prefs = MediaPreferences(
            enabled=True,
            type="storybook",
            model_name="model",
            text_position="none",
        )

        result = await mode.build_prompt_context(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=prefs,
        )
        # text_position='none' should not emit the note
        assert "DEFAULT TEXT POSITION" not in result

    async def test_build_prompt_context_genre_exception_handled_gracefully(self):
        from ii_agent.chat.media.modes.storybook_mode import StorybookModeStrategy
        from ii_agent.chat.types import MediaPreferences

        mode = StorybookModeStrategy()
        prefs = MediaPreferences(
            enabled=True,
            type="storybook",
            model_name="model",
            genre="fun_playful",
        )

        with patch("ii_agent.chat.media.modes.storybook_mode.MediaTemplateService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.get_media_template_by_name = AsyncMock(side_effect=Exception("DB error"))
            mock_svc_cls.return_value = mock_svc

            # Should not raise
            result = await mode.build_prompt_context(
                db_session=AsyncMock(),
                session_id="s1",
                media_preferences=prefs,
            )
        assert isinstance(result, str)


# ===========================================================================
# TemplateReferenceModeStrategy
# ===========================================================================


class TestTemplateReferenceModeStrategy:
    def test_should_clear_context_defaults_to_false(self):
        from ii_agent.chat.media.modes.template_reference_mode import (
            TemplateReferenceModeStrategy,
        )

        mode = TemplateReferenceModeStrategy()
        assert mode.should_clear_context() is False

    def test_should_clear_context_can_be_set_true(self):
        from ii_agent.chat.media.modes.template_reference_mode import (
            TemplateReferenceModeStrategy,
        )

        mode = TemplateReferenceModeStrategy(clear_context=True)
        assert mode.should_clear_context() is True

    def test_get_mode_name_returns_template_reference(self):
        from ii_agent.chat.media.modes.template_reference_mode import (
            TemplateReferenceModeStrategy,
        )

        mode = TemplateReferenceModeStrategy()
        assert mode.get_mode_name() == "template_reference"

    async def test_build_prompt_context_no_template_id_returns_empty(self):
        from ii_agent.chat.media.modes.template_reference_mode import (
            TemplateReferenceModeStrategy,
        )

        mode = TemplateReferenceModeStrategy()
        prefs = _make_prefs(template_id=None)

        result = await mode.build_prompt_context(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=prefs,
        )
        assert result == ""

    async def test_build_prompt_context_with_template_but_no_preview_returns_empty(self):
        from ii_agent.chat.media.modes.template_reference_mode import (
            TemplateReferenceModeStrategy,
        )

        mode = TemplateReferenceModeStrategy()
        prefs = _make_prefs(template_id="tmpl-1")

        with patch(
            "ii_agent.chat.media.modes.template_reference_mode.MediaTemplateService"
        ) as mock_svc_cls:
            mock_svc = MagicMock()
            mock_template = SimpleNamespace(name="T", prompt=None, preview=None)
            mock_svc.get_media_template_by_id = AsyncMock(return_value=mock_template)
            mock_svc_cls.return_value = mock_svc

            result = await mode.build_prompt_context(
                db_session=AsyncMock(),
                session_id="s1",
                media_preferences=prefs,
            )
        assert result == ""

    async def test_build_prompt_context_with_preview_url_returns_style_context(self):
        from ii_agent.chat.media.modes.template_reference_mode import (
            TemplateReferenceModeStrategy,
        )

        mode = TemplateReferenceModeStrategy()
        prefs = _make_prefs(template_id="tmpl-1")

        with patch(
            "ii_agent.chat.media.modes.template_reference_mode.MediaTemplateService"
        ) as mock_svc_cls:
            mock_svc = MagicMock()
            mock_template = SimpleNamespace(
                name="My Template",
                prompt="Use bold layout",
                preview="https://preview.url/img.jpg",
            )
            mock_svc.get_media_template_by_id = AsyncMock(return_value=mock_template)
            mock_svc_cls.return_value = mock_svc

            result = await mode.build_prompt_context(
                db_session=AsyncMock(),
                session_id="s1",
                media_preferences=prefs,
            )
        assert "Template Style Reference" in result
        assert "My Template" in result

    async def test_get_template_preview_url_returns_none_when_no_template_id(self):
        from ii_agent.chat.media.modes.template_reference_mode import (
            TemplateReferenceModeStrategy,
        )

        mode = TemplateReferenceModeStrategy()
        prefs = _make_prefs(template_id=None)

        url = await mode.get_template_preview_url(
            db_session=AsyncMock(),
            session_id="s1",
            media_preferences=prefs,
        )
        assert url is None

    async def test_get_template_preview_url_cached_after_first_call(self):
        """Second call should NOT invoke the DB again."""
        from ii_agent.chat.media.modes.template_reference_mode import (
            TemplateReferenceModeStrategy,
        )

        mode = TemplateReferenceModeStrategy()
        prefs = _make_prefs(template_id="tmpl-1")

        call_count = 0

        with patch(
            "ii_agent.chat.media.modes.template_reference_mode.MediaTemplateService"
        ) as mock_svc_cls:

            async def _mock_get(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return SimpleNamespace(name="T", prompt=None, preview="http://cached.url")

            mock_svc = MagicMock()
            mock_svc.get_media_template_by_id = _mock_get
            mock_svc_cls.return_value = mock_svc

            db = AsyncMock()
            url1 = await mode.get_template_preview_url(
                db_session=db, session_id="s1", media_preferences=prefs
            )
            url2 = await mode.get_template_preview_url(
                db_session=db, session_id="s1", media_preferences=prefs
            )

        assert url1 == "http://cached.url"
        assert url2 == "http://cached.url"
        assert call_count == 1  # DB called only once

    async def test_build_prompt_context_handles_service_exception(self):
        from ii_agent.chat.media.modes.template_reference_mode import (
            TemplateReferenceModeStrategy,
        )

        mode = TemplateReferenceModeStrategy()
        prefs = _make_prefs(template_id="tmpl-1")

        with patch(
            "ii_agent.chat.media.modes.template_reference_mode.MediaTemplateService"
        ) as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.get_media_template_by_id = AsyncMock(side_effect=Exception("Service failed"))
            mock_svc_cls.return_value = mock_svc

            result = await mode.build_prompt_context(
                db_session=AsyncMock(),
                session_id="s1",
                media_preferences=prefs,
            )
        # Should return empty string when exception occurs
        assert result == ""
