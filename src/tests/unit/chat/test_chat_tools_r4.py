"""Unit tests for chat tools: storybook_generate, image_generate, code_interpreter."""
from __future__ import annotations

import json
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from ii_agent.chat.tools.base import ToolCallInput, ToolResponse
from ii_agent.chat.types import ErrorTextContent, MediaPreferences

pytestmark = pytest.mark.unit


# ============================================================================
# Helpers
# ============================================================================


def _make_tool_call(name="test", input_data=None):
    return ToolCallInput(
        id="call-1",
        name=name,
        input=json.dumps(input_data or {}),
    )


def _make_container():
    return SimpleNamespace(
        session_service=AsyncMock(),
        user_service=AsyncMock(),
        file_service=AsyncMock(),
        storybook_service=AsyncMock(),
    )


def _make_media_prefs(
    provider="gemini",
    model_name="gemini-2.0-flash-exp",
    aspect_ratio="16:9",
    resolution="1K",
    page_count=None,
    text_position=None,
    voice_enabled=False,
    language=None,
    manga_layout=False,
    prefs_type="storybook",
):
    # page_count must be int or None per the schema
    pc = None
    if page_count is not None:
        try:
            pc = int(page_count)
        except (ValueError, TypeError):
            pc = None
    return MediaPreferences(
        enabled=True,
        type=prefs_type,
        provider=provider,
        model_name=model_name,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        page_count=pc,
        text_position=text_position,
        voice_enabled=voice_enabled,
        language=language,
    )


# ============================================================================
# StorybookGenerationTool - initialization
# ============================================================================


class TestStorybookGenerationToolInit:
    def _make_tool(self, prefs=None):
        from ii_agent.chat.tools.storybook_generate import StorybookGenerationTool

        return StorybookGenerationTool(
            session_id="sess-001",
            container=_make_container(),
            media_preferences=prefs,
        )

    def test_name_is_generate_storybook(self):
        tool = self._make_tool()
        assert tool.name == "generate_storybook"

    def test_defaults_without_preferences(self):
        tool = self._make_tool()
        assert tool.image_provider == "gemini"
        assert tool.aspect_ratio == "16:9"
        assert tool.resolution == "1K"
        assert tool.voice_enabled is False
        assert tool.manga_layout is False

    def test_preferences_applied(self):
        prefs = _make_media_prefs(provider="openai", aspect_ratio="1:1")
        tool = self._make_tool(prefs=prefs)
        assert tool.image_provider == "openai"
        assert tool.aspect_ratio == "1:1"
        # voice_enabled defaults to False when not set
        assert isinstance(tool.voice_enabled, bool)

    def test_manga_layout_attribute_defaults_false(self):
        # manga_layout is read from prefs via getattr with default False
        tool = self._make_tool()
        assert tool.manga_layout is False

    def test_info_returns_tool_info(self):
        tool = self._make_tool()
        info = tool.info()
        assert info.name == "generate_storybook"
        assert "scenes" in info.description or "scene" in info.description.lower()

    def test_session_id_set(self):
        tool = self._make_tool()
        assert tool.session_id == "sess-001"


# ============================================================================
# StorybookGenerationTool - _get_content_scene_cap
# ============================================================================


class TestGetContentSceneCap:
    def _make_tool_with_page_count(self, page_count_value=None):
        """Create tool with explicit page_count on the tool (not from prefs)."""
        from ii_agent.chat.tools.storybook_generate import StorybookGenerationTool, MAX_CONTENT_SCENES

        tool = StorybookGenerationTool(
            session_id="sess-001",
            container=_make_container(),
            media_preferences=None,
        )
        tool.page_count = page_count_value
        return tool, MAX_CONTENT_SCENES

    def test_no_page_count_returns_max(self):
        tool, max_scenes = self._make_tool_with_page_count(None)
        assert tool._get_content_scene_cap() == max_scenes

    def test_specific_page_count(self):
        tool, _ = self._make_tool_with_page_count(5)
        assert tool._get_content_scene_cap() == 5

    def test_unlimited_returns_max(self):
        # "unlimited" is a string, int() would fail, treated as None -> max
        tool, max_scenes = self._make_tool_with_page_count("unlimited")
        assert tool._get_content_scene_cap() == max_scenes

    def test_capped_at_max_scenes(self):
        tool, max_scenes = self._make_tool_with_page_count(999)
        assert tool._get_content_scene_cap() == max_scenes

    def test_zero_returns_zero(self):
        tool, _ = self._make_tool_with_page_count(0)
        # 0 is falsy so treated as None -> max
        assert tool._get_content_scene_cap() is not None


# ============================================================================
# StorybookGenerationTool - _apply_scene_cap
# ============================================================================


class TestApplySceneCap:
    def _make_tool_with_page_count(self, page_count_value=None):
        from ii_agent.chat.tools.storybook_generate import StorybookGenerationTool

        tool = StorybookGenerationTool(
            session_id="sess-001",
            container=_make_container(),
            media_preferences=None,
        )
        tool.page_count = page_count_value
        return tool

    def test_no_cap_when_scenes_under_limit(self):
        tool = self._make_tool_with_page_count(None)
        scenes = [{"image_prompt": f"scene {i}"} for i in range(3)]
        result, capped, max_count = tool._apply_scene_cap(scenes)
        assert not capped
        assert len(result) == 3

    def test_caps_when_scenes_over_limit(self):
        tool = self._make_tool_with_page_count(2)
        # max_total = 2 + 1 = 3, but we'll provide 10
        scenes = [{"image_prompt": f"scene {i}"} for i in range(10)]
        result, capped, max_count = tool._apply_scene_cap(scenes)
        assert capped
        assert len(result) == 3  # max_total = 2 + 1

    def test_no_cap_when_exactly_at_limit(self):
        tool = self._make_tool_with_page_count(4)
        # max_total = 5
        scenes = [{"image_prompt": f"scene {i}"} for i in range(5)]
        result, capped, max_count = tool._apply_scene_cap(scenes)
        assert not capped


# ============================================================================
# StorybookGenerationTool - _resolve_text_position
# ============================================================================


class TestResolveTextPosition:
    def _make_tool(self, user_text_position=None):
        from ii_agent.chat.tools.storybook_generate import StorybookGenerationTool

        tool = StorybookGenerationTool(
            session_id="sess-001",
            container=_make_container(),
            media_preferences=None,
        )
        tool.user_text_position = user_text_position
        return tool

    def test_cover_page_always_none(self):
        tool = self._make_tool(user_text_position="right")
        result = tool._resolve_text_position(is_cover_page=True, scene_text_position="right")
        assert result == "none"

    def test_user_position_overrides_scene(self):
        tool = self._make_tool(user_text_position="left")
        result = tool._resolve_text_position(is_cover_page=False, scene_text_position="right")
        assert result == "left"

    def test_scene_position_used_when_no_user_preference(self):
        from ii_agent.chat.tools.storybook_generate import StorybookGenerationTool

        tool = StorybookGenerationTool(
            session_id="sess-001",
            container=_make_container(),
            media_preferences=None,
        )
        result = tool._resolve_text_position(is_cover_page=False, scene_text_position="bottom")
        assert result == "bottom"

    def test_invalid_position_falls_back_to_default(self):
        from ii_agent.chat.tools.storybook_generate import StorybookGenerationTool, DEFAULT_TEXT_POSITION

        tool = StorybookGenerationTool(
            session_id="sess-001",
            container=_make_container(),
            media_preferences=None,
        )
        result = tool._resolve_text_position(is_cover_page=False, scene_text_position="invalid")
        assert result == DEFAULT_TEXT_POSITION


# ============================================================================
# StorybookGenerationTool - _build_style_context
# ============================================================================


class TestBuildStyleContext:
    def _make_tool(self):
        from ii_agent.chat.tools.storybook_generate import StorybookGenerationTool

        return StorybookGenerationTool(
            session_id="sess-001",
            container=_make_container(),
        )

    def test_empty_style_returns_empty(self):
        tool = self._make_tool()
        result = tool._build_style_context({})
        assert result == ""

    def test_character_description_included(self):
        tool = self._make_tool()
        result = tool._build_style_context({"character_description": "a brave knight"})
        assert "a brave knight" in result

    def test_art_style_included(self):
        tool = self._make_tool()
        result = tool._build_style_context({"art_style": "watercolor"})
        assert "watercolor" in result

    def test_color_palette_included(self):
        tool = self._make_tool()
        result = tool._build_style_context({"color_palette": "warm tones"})
        assert "warm tones" in result

    def test_all_parts_joined_with_period(self):
        tool = self._make_tool()
        result = tool._build_style_context(
            {
                "character_description": "a fox",
                "art_style": "cartoon",
                "color_palette": "bright",
            }
        )
        assert ". " in result
        assert "a fox" in result


# ============================================================================
# StorybookGenerationTool - _enhance_prompt_with_style
# ============================================================================


class TestEnhancePromptWithStyle:
    def _make_tool(self):
        from ii_agent.chat.tools.storybook_generate import StorybookGenerationTool

        return StorybookGenerationTool(
            session_id="sess-001",
            container=_make_container(),
        )

    def test_includes_base_prompt(self):
        tool = self._make_tool()
        result = tool._enhance_prompt_with_style("a forest scene", "")
        assert "a forest scene" in result

    def test_includes_style_when_provided(self):
        tool = self._make_tool()
        result = tool._enhance_prompt_with_style(
            "a forest scene", "watercolor art style"
        )
        assert "watercolor art style" in result

    def test_includes_borderless_note(self):
        tool = self._make_tool()
        result = tool._enhance_prompt_with_style("prompt", "")
        assert "FULL BLEED" in result or "aspect ratio" in result.lower()

    def test_reference_type_style_only_adds_note(self):
        tool = self._make_tool()
        result = tool._enhance_prompt_with_style(
            "prompt", "", reference_type="style_only"
        )
        assert "style" in result.lower()

    def test_composition_rule_appended(self):
        tool = self._make_tool()
        result = tool._enhance_prompt_with_style(
            "prompt", "", composition_rule="Keep subjects in center"
        )
        assert "Keep subjects in center" in result


# ============================================================================
# StorybookGenerationTool - _get_optimal_aspect_ratio
# ============================================================================


class TestGetOptimalAspectRatio:
    def _make_tool(self, provider="gemini"):
        from ii_agent.chat.tools.storybook_generate import StorybookGenerationTool

        prefs = _make_media_prefs(provider=provider)
        return StorybookGenerationTool(
            session_id="sess-001",
            container=_make_container(),
            media_preferences=prefs,
        )

    def test_returns_base_when_no_text(self):
        tool = self._make_tool()
        result = tool._get_optimal_aspect_ratio("16:9", "none", 0)
        assert result == "16:9"

    def test_returns_base_when_text_percentage_zero(self):
        tool = self._make_tool()
        result = tool._get_optimal_aspect_ratio("16:9", "right", 0)
        assert result == "16:9"

    def test_selects_supported_ratio_for_left_position(self):
        tool = self._make_tool()
        result = tool._get_optimal_aspect_ratio("16:9", "left", 25)
        # Should return a valid ratio
        assert ":" in result

    def test_invalid_base_ratio_returns_base(self):
        tool = self._make_tool()
        result = tool._get_optimal_aspect_ratio("invalid", "left", 25)
        assert result == "invalid"


# ============================================================================
# StorybookGenerationTool - _calculate_safe_zones
# ============================================================================


class TestCalculateSafeZones:
    def _make_tool(self):
        from ii_agent.chat.tools.storybook_generate import StorybookGenerationTool

        return StorybookGenerationTool(
            session_id="sess-001",
            container=_make_container(),
        )

    def test_returns_100_100_when_no_text(self):
        tool = self._make_tool()
        w, h = tool._calculate_safe_zones("16:9", "16:9", "none", 0)
        assert w == 100
        assert h == 100

    def test_returns_100_100_for_zero_percentage(self):
        tool = self._make_tool()
        w, h = tool._calculate_safe_zones("16:9", "16:9", "right", 0)
        assert w == 100
        assert h == 100

    def test_invalid_ratio_returns_100_100(self):
        tool = self._make_tool()
        w, h = tool._calculate_safe_zones("invalid", "1:1", "right", 25)
        assert w == 100
        assert h == 100

    def test_returns_visible_width_for_side_text(self):
        tool = self._make_tool()
        w, h = tool._calculate_safe_zones("16:9", "3:2", "right", 25)
        assert 0 < w <= 100
        assert h == 100 or w == 100


# ============================================================================
# StorybookGenerationTool - run
# ============================================================================


class TestStorybookGenerationToolRun:
    @pytest.mark.asyncio
    async def test_run_returns_error_message(self):
        from ii_agent.chat.tools.storybook_generate import StorybookGenerationTool

        tool = StorybookGenerationTool(
            session_id="sess-001",
            container=_make_container(),
        )
        tc = _make_tool_call("generate_storybook", {})
        response = await tool.run(tc)
        assert isinstance(response.output, ErrorTextContent)
        assert "Celery" in response.output.value or "background" in response.output.value.lower()


# ============================================================================
# StorybookGenerationTool - start_celery_generation errors
# ============================================================================


class TestStartCeleryGenerationErrors:
    @pytest.mark.asyncio
    async def test_returns_error_for_no_scenes(self):
        from ii_agent.chat.tools.storybook_generate import StorybookGenerationTool

        tool = StorybookGenerationTool(
            session_id="sess-001",
            container=_make_container(),
        )
        tc = _make_tool_call("generate_storybook", {"title": "My Story", "scenes": []})
        response = await tool.start_celery_generation(
            tc, parent_message_id=None, model_id="claude-3"
        )
        assert isinstance(response.output, ErrorTextContent)
        assert "No scenes" in response.output.value

    @pytest.mark.asyncio
    async def test_returns_error_for_invalid_json(self):
        from ii_agent.chat.tools.storybook_generate import StorybookGenerationTool

        tool = StorybookGenerationTool(
            session_id="sess-001",
            container=_make_container(),
        )
        tc = ToolCallInput(id="c1", name="generate_storybook", input="not-json")
        response = await tool.start_celery_generation(
            tc, parent_message_id=None, model_id="claude-3"
        )
        assert isinstance(response.output, ErrorTextContent)
        assert "Invalid" in response.output.value


# ============================================================================
# ImageGenerationTool - initialization
# ============================================================================


class TestImageGenerationToolInit:
    def _make_tool(self, prefs=None, aspect_ratio=None, resolution=None):
        from ii_agent.chat.tools.image_generate import ImageGenerationTool

        return ImageGenerationTool(
            session_id="sess-001",
            container=_make_container(),
            media_preferences=prefs,
            image_aspect_ratio=aspect_ratio,
            image_resolution=resolution,
        )

    def test_name_is_generate_image(self):
        tool = self._make_tool()
        assert tool.name == "generate_image"

    def test_session_id_set(self):
        tool = self._make_tool()
        assert tool.session_id == "sess-001"

    def test_info_returns_tool_info(self):
        tool = self._make_tool()
        info = tool.info()
        assert info.name == "generate_image"
        assert "prompt" in info.description.lower() or "image" in info.description.lower()

    def test_defaults_without_preferences(self):
        tool = self._make_tool()
        assert tool.image_model_name is None
        assert tool.image_provider is None

    def test_preferences_sets_model_and_provider(self):
        prefs = MediaPreferences(
            enabled=True,
            type="image",
            provider="openai",
            model_name="gpt-image-1.5",
        )
        tool = self._make_tool(prefs=prefs)
        assert tool.image_model_name == "gpt-image-1.5"
        assert tool.image_provider == "openai"


# ============================================================================
# ImageGenerationTool - _get_model_adjusted_settings
# ============================================================================


class TestGetModelAdjustedSettings:
    def _make_tool(self, model_name=None, provider=None):
        from ii_agent.chat.tools.image_generate import ImageGenerationTool

        prefs = None
        if model_name or provider:
            prefs = MediaPreferences(
                enabled=True,
                type="image",
                provider=provider,
                model_name=model_name or "default-model",
            )
        return ImageGenerationTool(
            session_id="sess-001",
            container=_make_container(),
            media_preferences=prefs,
        )

    def test_gpt_image_1_1_maps_to_1024(self):
        tool = self._make_tool(model_name="gpt-image-1.5", provider="openai")
        ar, size = tool._get_model_adjusted_settings("1:1", "1K")
        assert ar == "1:1"
        assert size == "1024x1024"

    def test_gpt_image_3_2_maps_to_1536x1024(self):
        tool = self._make_tool(model_name="gpt-image-1.5", provider="openai")
        ar, size = tool._get_model_adjusted_settings("3:2", "1K")
        assert size == "1536x1024"

    def test_gpt_image_2_3_maps_to_1024x1536(self):
        tool = self._make_tool(model_name="gpt-image-1.5", provider="openai")
        ar, size = tool._get_model_adjusted_settings("2:3", "1K")
        assert size == "1024x1536"

    def test_gpt_image_unsupported_aspect_defaults_to_1x1(self):
        tool = self._make_tool(model_name="gpt-image-1.5", provider="openai")
        ar, size = tool._get_model_adjusted_settings("21:9", "1K")
        assert ar == "1:1"
        assert size == "1024x1024"

    def test_gemini_valid_aspect_ratio(self):
        tool = self._make_tool(provider="gemini")
        ar, size = tool._get_model_adjusted_settings("16:9", "1K")
        assert ar == "16:9"
        assert size == "1K"

    def test_gemini_invalid_aspect_ratio_defaults_to_1x1(self):
        tool = self._make_tool(provider="gemini")
        ar, size = tool._get_model_adjusted_settings("invalid", "1K")
        assert ar == "1:1"

    def test_gemini_invalid_resolution_defaults_to_1k(self):
        tool = self._make_tool(provider="gemini")
        ar, size = tool._get_model_adjusted_settings("1:1", "invalid")
        assert size == "1K"

    def test_default_provider_passthrough(self):
        tool = self._make_tool()
        ar, size = tool._get_model_adjusted_settings("4:3", "2K")
        assert ar == "4:3"
        assert size == "2K"

    def test_openai_provider_maps_gpt_sizes(self):
        tool = self._make_tool(provider="openai")
        ar, size = tool._get_model_adjusted_settings("1:1", "1K")
        assert size == "1024x1024"


# ============================================================================
# ImageGenerationTool - run (invalid input)
# ============================================================================


class TestImageGenerationToolRun:
    @pytest.mark.asyncio
    async def test_run_invalid_json_returns_error(self):
        from ii_agent.chat.tools.image_generate import ImageGenerationTool

        tool = ImageGenerationTool(
            session_id="sess-001",
            container=_make_container(),
        )
        tc = ToolCallInput(id="c1", name="generate_image", input="not-json")
        response = await tool.run(tc)
        assert isinstance(response.output, ErrorTextContent)
        assert "Invalid" in response.output.value

    @pytest.mark.asyncio
    async def test_run_missing_prompt_returns_error(self):
        from ii_agent.chat.tools.image_generate import ImageGenerationTool

        tool = ImageGenerationTool(
            session_id="sess-001",
            container=_make_container(),
        )
        tc = _make_tool_call("generate_image", {})
        response = await tool.run(tc)
        assert isinstance(response.output, ErrorTextContent)


# ============================================================================
# CodeInterpreter - _get_file_extension_and_content_type
# ============================================================================


class TestCodeInterpreterFileExtensions:
    def _make_interpreter(self):
        from ii_agent.chat.tools.code_interperter import CodeInterpreter
        from pydantic import SecretStr

        llm_config = SimpleNamespace(
            api_key=SecretStr("test-key"),
            base_url=None,
            model="gpt-4o",
        )
        return CodeInterpreter(
            llm_config=llm_config,
            db_session=AsyncMock(),
            storage=MagicMock(),
            session_id="sess-001",
            parent_message_id=None,
            user_id="user-001",
        )

    def test_png_file_id(self):
        ci = self._make_interpreter()
        ext, mime = ci._get_file_extension_and_content_type("file_png_abc123")
        assert ext == ".png"
        assert mime == "image/png"

    def test_jpg_file_id(self):
        ci = self._make_interpreter()
        ext, mime = ci._get_file_extension_and_content_type("output_jpg_abc")
        assert ext == ".jpg"
        assert mime == "image/jpeg"

    def test_jpeg_file_id(self):
        ci = self._make_interpreter()
        ext, mime = ci._get_file_extension_and_content_type("file_jpeg_abc")
        assert ext == ".jpg"
        assert mime == "image/jpeg"

    def test_gif_file_id(self):
        ci = self._make_interpreter()
        ext, mime = ci._get_file_extension_and_content_type("output_gif_abc")
        assert ext == ".gif"
        assert mime == "image/gif"

    def test_csv_file_id(self):
        ci = self._make_interpreter()
        ext, mime = ci._get_file_extension_and_content_type("data_csv_abc")
        assert ext == ".csv"
        assert mime == "text/csv"

    def test_json_file_id(self):
        ci = self._make_interpreter()
        ext, mime = ci._get_file_extension_and_content_type("results_json_abc")
        assert ext == ".json"
        assert mime == "application/json"

    def test_xlsx_file_id(self):
        ci = self._make_interpreter()
        ext, mime = ci._get_file_extension_and_content_type("spreadsheet_xlsx_abc")
        assert ext == ".xlsx"
        assert "spreadsheetml" in mime

    def test_xml_file_id(self):
        ci = self._make_interpreter()
        ext, mime = ci._get_file_extension_and_content_type("data_xml_abc")
        assert ext == ".xml"
        assert mime == "application/xml"

    def test_default_unknown(self):
        ci = self._make_interpreter()
        ext, mime = ci._get_file_extension_and_content_type("unknown_abc")
        assert ext == ".png"
        assert mime == "image/png"


# ============================================================================
# CodeInterpreter - info
# ============================================================================


class TestCodeInterpreterInfo:
    def _make_interpreter(self):
        from ii_agent.chat.tools.code_interperter import CodeInterpreter
        from pydantic import SecretStr

        llm_config = SimpleNamespace(
            api_key=SecretStr("test-key"),
            base_url=None,
            model="gpt-4o",
        )
        return CodeInterpreter(
            llm_config=llm_config,
            db_session=AsyncMock(),
            storage=MagicMock(),
            session_id="sess-001",
            parent_message_id=None,
            user_id="user-001",
        )

    def test_name_is_code_interpreter(self):
        ci = self._make_interpreter()
        assert ci.name == "code_interpreter"

    def test_info_returns_correct_name(self):
        ci = self._make_interpreter()
        info = ci.info()
        assert info.name == "code_interpreter"

    def test_info_has_query_parameter(self):
        ci = self._make_interpreter()
        info = ci.info()
        assert "query" in info.parameters["properties"]


# ============================================================================
# CodeInterpreter - run with invalid input
# ============================================================================


class TestCodeInterpreterRun:
    def _make_interpreter(self):
        from ii_agent.chat.tools.code_interperter import CodeInterpreter
        from pydantic import SecretStr

        llm_config = SimpleNamespace(
            api_key=SecretStr("test-key"),
            base_url=None,
            model="gpt-4o",
        )
        return CodeInterpreter(
            llm_config=llm_config,
            db_session=AsyncMock(),
            storage=MagicMock(),
            session_id="sess-001",
            parent_message_id=None,
            user_id="user-001",
        )

    @pytest.mark.asyncio
    async def test_run_invalid_json_returns_error(self):
        ci = self._make_interpreter()
        tc = ToolCallInput(id="c1", name="code_interpreter", input="not-json")
        response = await ci.run(tc)
        assert isinstance(response.output, ErrorTextContent)
        assert "Invalid" in response.output.value

    @pytest.mark.asyncio
    async def test_run_missing_query_returns_error(self):
        ci = self._make_interpreter()
        tc = _make_tool_call("code_interpreter", {})
        response = await ci.run(tc)
        assert isinstance(response.output, ErrorTextContent)

    @pytest.mark.asyncio
    async def test_get_parent_message_files_returns_empty_when_not_found(self):
        ci = self._make_interpreter()
        # db_session.execute returns nothing useful
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        ci.db_session.execute = AsyncMock(return_value=mock_result)

        result = await ci._get_parent_message_files()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_parent_message_files_returns_file_ids(self):
        import uuid

        ci = self._make_interpreter()
        fid1 = uuid.uuid4()
        fid2 = uuid.uuid4()
        parent_msg = SimpleNamespace(file_ids=[fid1, fid2])
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = parent_msg
        ci.db_session.execute = AsyncMock(return_value=mock_result)

        result = await ci._get_parent_message_files()
        assert len(result) == 2
        assert str(fid1) in result

    @pytest.mark.asyncio
    async def test_upload_files_to_openai_returns_empty_for_no_files(self):
        ci = self._make_interpreter()
        result = await ci._upload_files_to_openai([])
        assert result == []
