"""Unit tests for ii_agent.chat.tools.storybook_generate – StorybookGenerationTool."""

from __future__ import annotations

import json
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.chat.tools.storybook_generate import (
    ALLOWED_TEXT_POSITIONS,
    DEFAULT_ASPECT_RATIO,
    DEFAULT_RESOLUTION,
    DEFAULT_TEXT_PERCENTAGE,
    DEFAULT_TEXT_POSITION,
    MAX_CONTENT_SCENES,
    STORYBOOK_TASK_EXPIRES_SECONDS,
    SUPPORTED_ASPECT_RATIOS_BY_PROVIDER,
    StorybookGenerationTool,
)
from ii_agent.chat.tools.base import ToolCallInput
from ii_agent.chat.types import MediaPreferences


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool(
    session_id: str = "sess-001",
    container=None,
    media_preferences=None,
) -> StorybookGenerationTool:
    container = container or MagicMock()
    return StorybookGenerationTool(
        session_id=session_id,
        container=container,
        media_preferences=media_preferences,
    )


def _media_prefs(**kwargs) -> MediaPreferences:
    defaults = {
        "enabled": True,
        "type": "storybook",
        "model_name": "gemini-2.0-flash-exp",
        "provider": "gemini",
        "aspect_ratio": "16:9",
        "resolution": "1K",
    }
    defaults.update(kwargs)
    return MediaPreferences(**defaults)


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------

class TestStorybookGenerationToolInit:
    def test_defaults_when_no_media_preferences(self):
        tool = _make_tool()
        assert tool.aspect_ratio == DEFAULT_ASPECT_RATIO
        assert tool.resolution == DEFAULT_RESOLUTION
        assert tool.image_provider == "gemini"
        assert tool.voice_enabled is False
        assert tool.manga_layout is False

    def test_uses_media_preferences_values(self):
        prefs = _media_prefs(aspect_ratio="1:1", resolution="2K", provider="openai")
        tool = _make_tool(media_preferences=prefs)
        assert tool.aspect_ratio == "1:1"
        assert tool.resolution == "2K"
        assert tool.image_provider == "openai"

    def test_storybook_tool_does_not_apply_manga_mode_overrides(self):
        prefs = MagicMock()
        prefs.model_name = "model"
        prefs.provider = "gemini"
        prefs.aspect_ratio = "16:9"
        prefs.resolution = "1K"
        prefs.page_count = None
        prefs.text_position = "right"
        prefs.voice_enabled = True
        prefs.language = None
        prefs.manga_layout = True

        tool = _make_tool(media_preferences=prefs)
        assert tool.manga_layout is False
        assert tool.voice_enabled is True
        assert tool.user_text_position == "right"

    def test_name_property(self):
        tool = _make_tool()
        assert tool.name == "generate_storybook"

    def test_session_id_stored(self):
        tool = _make_tool(session_id="my-session")
        assert tool.session_id == "my-session"


# ---------------------------------------------------------------------------
# info()
# ---------------------------------------------------------------------------

class TestStorybookGenerationToolInfo:
    def test_info_returns_tool_info(self):
        from ii_agent.chat.tools.base import ToolInfo
        tool = _make_tool()
        info = tool.info()
        assert isinstance(info, ToolInfo)
        assert info.name == "generate_storybook"
        assert "scenes" in info.parameters["properties"]
        assert "title" in info.parameters["properties"]

    def test_info_description_mentions_storybook(self):
        tool = _make_tool()
        info = tool.info()
        assert "storybook" in info.description.lower()

    def test_info_required_fields(self):
        tool = _make_tool()
        info = tool.info()
        assert "title" in info.required
        assert "scenes" in info.required


# ---------------------------------------------------------------------------
# _get_content_scene_cap
# ---------------------------------------------------------------------------

class TestGetContentSceneCap:
    def test_returns_max_when_page_count_none(self):
        tool = _make_tool()
        assert tool._get_content_scene_cap() == MAX_CONTENT_SCENES

    def test_returns_max_when_page_count_unlimited(self):
        prefs = MagicMock()
        prefs.model_name = None
        prefs.provider = "gemini"
        prefs.aspect_ratio = "16:9"
        prefs.resolution = "1K"
        prefs.page_count = "unlimited"
        prefs.text_position = None
        prefs.voice_enabled = False
        prefs.language = None
        prefs.manga_layout = False
        tool = _make_tool(media_preferences=prefs)
        assert tool._get_content_scene_cap() == MAX_CONTENT_SCENES

    def test_respects_numeric_page_count(self):
        prefs = MagicMock()
        prefs.model_name = None
        prefs.provider = "gemini"
        prefs.aspect_ratio = "16:9"
        prefs.resolution = "1K"
        prefs.page_count = 5
        prefs.text_position = None
        prefs.voice_enabled = False
        prefs.language = None
        prefs.manga_layout = False
        tool = _make_tool(media_preferences=prefs)
        assert tool._get_content_scene_cap() == 5

    def test_clamps_page_count_to_max(self):
        prefs = MagicMock()
        prefs.model_name = None
        prefs.provider = "gemini"
        prefs.aspect_ratio = "16:9"
        prefs.resolution = "1K"
        prefs.page_count = 9999
        prefs.text_position = None
        prefs.voice_enabled = False
        prefs.language = None
        prefs.manga_layout = False
        tool = _make_tool(media_preferences=prefs)
        assert tool._get_content_scene_cap() == MAX_CONTENT_SCENES

    def test_clamps_to_zero_for_negative_page_count(self):
        prefs = MagicMock()
        prefs.model_name = None
        prefs.provider = "gemini"
        prefs.aspect_ratio = "16:9"
        prefs.resolution = "1K"
        prefs.page_count = -1
        prefs.text_position = None
        prefs.voice_enabled = False
        prefs.language = None
        prefs.manga_layout = False
        tool = _make_tool(media_preferences=prefs)
        assert tool._get_content_scene_cap() == 0


# ---------------------------------------------------------------------------
# _apply_scene_cap
# ---------------------------------------------------------------------------

class TestApplySceneCap:
    def test_does_not_cap_when_within_limit(self):
        tool = _make_tool()
        scenes = [{"image_prompt": f"scene {i}", "text_content": "text"} for i in range(3)]
        capped_scenes, capped, max_content = tool._apply_scene_cap(scenes)
        assert capped is False
        assert len(capped_scenes) == 3

    def test_caps_when_over_limit(self):
        tool = _make_tool()
        scenes = [{"image_prompt": f"scene {i}"} for i in range(MAX_CONTENT_SCENES + 10)]
        capped_scenes, capped, max_content = tool._apply_scene_cap(scenes)
        assert capped is True
        assert len(capped_scenes) == MAX_CONTENT_SCENES + 1  # +1 for cover


# ---------------------------------------------------------------------------
# _resolve_text_position
# ---------------------------------------------------------------------------

class TestResolveTextPosition:
    def test_cover_page_always_returns_none(self):
        tool = _make_tool()
        result = tool._resolve_text_position(is_cover_page=True, scene_text_position="right")
        assert result == "none"

    def test_uses_user_text_position_when_set(self):
        prefs = MagicMock()
        prefs.model_name = None
        prefs.provider = "gemini"
        prefs.aspect_ratio = "16:9"
        prefs.resolution = "1K"
        prefs.page_count = None
        prefs.text_position = "left"
        prefs.voice_enabled = False
        prefs.language = None
        prefs.manga_layout = False
        tool = _make_tool(media_preferences=prefs)
        result = tool._resolve_text_position(is_cover_page=False, scene_text_position="right")
        assert result == "left"

    def test_falls_back_to_scene_text_position(self):
        tool = _make_tool()
        tool.user_text_position = None
        result = tool._resolve_text_position(is_cover_page=False, scene_text_position="top")
        assert result == "top"

    def test_falls_back_to_default_when_neither_set(self):
        tool = _make_tool()
        tool.user_text_position = None
        result = tool._resolve_text_position(is_cover_page=False, scene_text_position=None)
        assert result == DEFAULT_TEXT_POSITION

    def test_returns_default_for_invalid_position(self):
        tool = _make_tool()
        tool.user_text_position = "invalid_position"
        result = tool._resolve_text_position(is_cover_page=False, scene_text_position=None)
        assert result == DEFAULT_TEXT_POSITION

    def test_allowed_text_positions_set(self):
        assert "left" in ALLOWED_TEXT_POSITIONS
        assert "right" in ALLOWED_TEXT_POSITIONS
        assert "top" in ALLOWED_TEXT_POSITIONS
        assert "bottom" in ALLOWED_TEXT_POSITIONS
        assert "none" in ALLOWED_TEXT_POSITIONS
        assert "separate_page" in ALLOWED_TEXT_POSITIONS


# ---------------------------------------------------------------------------
# _build_style_context
# ---------------------------------------------------------------------------

class TestBuildStyleContext:
    def test_returns_empty_string_when_no_style(self):
        tool = _make_tool()
        result = tool._build_style_context({})
        assert result == ""

    def test_includes_character_description(self):
        tool = _make_tool()
        result = tool._build_style_context({"character_description": "a brave knight"})
        assert "a brave knight" in result

    def test_includes_art_style(self):
        tool = _make_tool()
        result = tool._build_style_context({"art_style": "watercolor"})
        assert "watercolor" in result

    def test_includes_color_palette(self):
        tool = _make_tool()
        result = tool._build_style_context({"color_palette": "warm tones"})
        assert "warm tones" in result

    def test_joins_multiple_parts(self):
        tool = _make_tool()
        result = tool._build_style_context({
            "art_style": "cartoon",
            "color_palette": "vibrant",
        })
        assert ". " in result


# ---------------------------------------------------------------------------
# _enhance_prompt_with_style
# ---------------------------------------------------------------------------

class TestEnhancePromptWithStyle:
    def test_includes_original_prompt(self):
        tool = _make_tool()
        result = tool._enhance_prompt_with_style("A cat", "", reference_type=None)
        assert "A cat" in result

    def test_includes_borderless_instructions(self):
        tool = _make_tool()
        result = tool._enhance_prompt_with_style("A cat", "", reference_type=None)
        assert "FULL BLEED" in result or "CRITICAL" in result

    def test_includes_style_context_when_provided(self):
        tool = _make_tool()
        result = tool._enhance_prompt_with_style("A dog", "Art style: cartoon", reference_type=None)
        assert "A dog" in result
        assert "cartoon" in result

    def test_includes_reference_note_for_style_only(self):
        tool = _make_tool()
        result = tool._enhance_prompt_with_style("A bird", "", reference_type="style_only")
        assert "art style" in result.lower()

    def test_includes_composition_rule_when_provided(self):
        tool = _make_tool()
        rule = "Keep subjects in the center"
        result = tool._enhance_prompt_with_style("A fox", "", composition_rule=rule)
        assert rule in result


# ---------------------------------------------------------------------------
# _get_optimal_aspect_ratio
# ---------------------------------------------------------------------------

class TestGetOptimalAspectRatio:
    def test_returns_base_when_no_text(self):
        tool = _make_tool()
        result = tool._get_optimal_aspect_ratio("16:9", "none", 0)
        assert result == "16:9"

    def test_returns_base_for_zero_text_percentage(self):
        tool = _make_tool()
        result = tool._get_optimal_aspect_ratio("16:9", "right", 0)
        assert result == "16:9"

    def test_selects_closest_ratio_for_left_text(self):
        tool = _make_tool()
        tool.image_provider = "gemini"
        result = tool._get_optimal_aspect_ratio("16:9", "left", 30)
        # Should return a valid gemini ratio
        assert result in SUPPORTED_ASPECT_RATIOS_BY_PROVIDER["gemini"]

    def test_returns_base_for_invalid_ratio(self):
        tool = _make_tool()
        result = tool._get_optimal_aspect_ratio("invalid", "right", 30)
        assert result == "invalid"

    def test_uses_gemini_provider_by_default(self):
        tool = _make_tool()
        tool.image_provider = "unknown_provider"
        result = tool._get_optimal_aspect_ratio("16:9", "left", 30)
        # Falls back to gemini defaults
        assert result in SUPPORTED_ASPECT_RATIOS_BY_PROVIDER["gemini"]


# ---------------------------------------------------------------------------
# _calculate_safe_zones
# ---------------------------------------------------------------------------

class TestCalculateSafeZones:
    def test_returns_100_100_for_none_position(self):
        tool = _make_tool()
        w, h = tool._calculate_safe_zones("16:9", "16:9", "none", 0)
        assert w == 100
        assert h == 100

    def test_returns_100_100_for_zero_percentage(self):
        tool = _make_tool()
        w, h = tool._calculate_safe_zones("16:9", "16:9", "right", 0)
        assert w == 100
        assert h == 100

    def test_returns_100_100_for_invalid_ratio(self):
        tool = _make_tool()
        w, h = tool._calculate_safe_zones("invalid", "16:9", "right", 30)
        assert w == 100
        assert h == 100

    def test_calculates_safe_zone_for_side_text(self):
        tool = _make_tool()
        w, h = tool._calculate_safe_zones("16:9", "3:2", "right", 30)
        assert 0 <= w <= 100
        assert 0 <= h <= 100

    def test_calculates_safe_zone_for_top_text(self):
        tool = _make_tool()
        w, h = tool._calculate_safe_zones("16:9", "21:9", "top", 30)
        assert 0 <= w <= 100
        assert 0 <= h <= 100


# ---------------------------------------------------------------------------
# run() always returns disabled error
# ---------------------------------------------------------------------------

class TestStorybookGenerationToolRun:
    @pytest.mark.asyncio
    async def test_run_returns_disabled_error(self):
        from ii_agent.chat.types import ErrorTextContent
        tool = _make_tool()
        call = ToolCallInput(id="c1", name="generate_storybook", input="{}")
        response = await tool.run(call)
        assert isinstance(response.output, ErrorTextContent)
        assert "Celery" in response.output.value or "disabled" in response.output.value


# ---------------------------------------------------------------------------
# start_celery_generation – guard clauses
# ---------------------------------------------------------------------------

class TestStartCeleryGeneration:
    @pytest.mark.asyncio
    async def test_returns_error_for_invalid_json_input(self):
        from ii_agent.chat.types import ErrorTextContent
        import uuid
        tool = _make_tool()
        call = ToolCallInput(id="c1", name="generate_storybook", input="invalid json")
        response = await tool.start_celery_generation(
            call, parent_message_id=uuid.uuid4(), model_id="test-model"
        )
        assert isinstance(response.output, ErrorTextContent)

    @pytest.mark.asyncio
    async def test_returns_error_when_no_scenes(self):
        from ii_agent.chat.types import ErrorTextContent
        import uuid
        tool = _make_tool()
        call = ToolCallInput(
            id="c1",
            name="generate_storybook",
            input=json.dumps({"title": "My Book", "scenes": []}),
        )
        response = await tool.start_celery_generation(
            call, parent_message_id=uuid.uuid4(), model_id="test-model"
        )
        assert isinstance(response.output, ErrorTextContent)
        assert "scenes" in response.output.value.lower() or "scene" in response.output.value.lower()


# ---------------------------------------------------------------------------
# _generate_voice_audio – guard clauses
# ---------------------------------------------------------------------------

class TestGenerateVoiceAudio:
    @pytest.mark.asyncio
    async def test_returns_none_cost_zero_when_voice_disabled(self):
        tool = _make_tool()
        tool.voice_enabled = False
        url, cost = await tool._generate_voice_audio("Some text")
        assert url is None
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_returns_none_when_text_is_empty(self):
        tool = _make_tool()
        tool.voice_enabled = True
        url, cost = await tool._generate_voice_audio("")
        assert url is None
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_returns_none_when_voice_service_unavailable(self):
        tool = _make_tool()
        tool.voice_enabled = True
        with patch.object(tool, "_get_voice_service", return_value=None):
            url, cost = await tool._generate_voice_audio("Some text")
        assert url is None
        assert cost == 0.0


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestModuleLevelConstants:
    def test_default_aspect_ratio(self):
        assert DEFAULT_ASPECT_RATIO == "16:9"

    def test_default_resolution(self):
        assert DEFAULT_RESOLUTION == "1K"

    def test_default_text_position(self):
        assert DEFAULT_TEXT_POSITION == "right"

    def test_default_text_percentage(self):
        assert DEFAULT_TEXT_PERCENTAGE == 30

    def test_max_content_scenes(self):
        assert MAX_CONTENT_SCENES == 50

    def test_task_expires_seconds(self):
        assert STORYBOOK_TASK_EXPIRES_SECONDS == 300

    def test_supported_providers(self):
        assert "gemini" in SUPPORTED_ASPECT_RATIOS_BY_PROVIDER
        assert "openai" in SUPPORTED_ASPECT_RATIOS_BY_PROVIDER

    def test_gemini_supports_more_ratios_than_openai(self):
        gemini_ratios = SUPPORTED_ASPECT_RATIOS_BY_PROVIDER["gemini"]
        openai_ratios = SUPPORTED_ASPECT_RATIOS_BY_PROVIDER["openai"]
        assert len(gemini_ratios) > len(openai_ratios)
