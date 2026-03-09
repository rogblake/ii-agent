"""Unit tests for ii_agent.content.slides.nano_banana.service – NanoBananaService."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.content.slides.nano_banana.service import (
    NanoBananaService,
    TEXT_COMPONENT_TYPES,
    # VISION_DETECTION_MODEL,
    _build_edit_summary,
    _inject_runtime_script,
    _parse_bounding_box,
    _parse_styles,
)
from ii_agent.content.slides.nano_banana.schemas import (
    BoundingBox,
    ComponentStyles,
    DetectedComponent,
    DetectRequest,
    DetectResponse,
    GetVersionsResponse,
    Instruction,
    InstructionType,
    RegenerateRequest,
    RegenerateResponse,
    RemoveBackgroundRequest,
    RemoveBackgroundResponse,
    RevertRequest,
    RevertResponse,
    Selection,
    SelectionType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _make_service(repo=None, gemini_api_key="test-key") -> NanoBananaService:
    repo = repo or MagicMock()
    return NanoBananaService(repo=repo, gemini_api_key=gemini_api_key)


def _detected_component(
    design_id: str = "nano-title-0",
    component_type: str = "title",
    text_content: str = "Hello",
) -> DetectedComponent:
    return DetectedComponent(
        design_id=design_id,
        component_type=component_type,
        label=component_type,
        text_content=text_content,
        bounding_box=BoundingBox(x=10, y=10, width=50, height=20),
        z_index=1,
        confidence=0.9,
    )


def _instruction(instruction_type: InstructionType, ai_prompt: str = "") -> Instruction:
    return Instruction(
        id="inst-1",
        selection=Selection(type=SelectionType.COMPONENT, component_id="nano-title-0"),
        instruction_type=instruction_type,
        ai_prompt=ai_prompt,
        timestamp=1000,
    )


# ---------------------------------------------------------------------------
# NanoBananaService instantiation
# ---------------------------------------------------------------------------

class TestNanoBananaServiceInit:
    def test_can_instantiate_with_api_key(self):
        service = _make_service(gemini_api_key="key-123")
        assert service._gemini_api_key == "key-123"

    def test_can_instantiate_with_gcp_project(self):
        service = NanoBananaService(
            repo=MagicMock(),
            gcp_project_id="my-proj",
            gcp_location="us-central1",
        )
        assert service._gcp_project_id == "my-proj"

    def test_vision_client_initially_none(self):
        service = _make_service()
        assert service._vision_client is None

    def test_slide_gen_config_initially_none(self):
        service = _make_service()
        assert service._slide_gen_config is None


# ---------------------------------------------------------------------------
# vision_client property
# ---------------------------------------------------------------------------

class TestVisionClientProperty:
    def test_raises_when_no_credentials(self):
        service = NanoBananaService(repo=MagicMock())
        with pytest.raises(RuntimeError, match="No Gemini API key"):
            _ = service.vision_client

    def test_uses_api_key_when_available(self):
        service = _make_service(gemini_api_key="my-key")
        with patch("ii_agent.content.slides.nano_banana.service.genai.Client") as mock_client:
            mock_client.return_value = MagicMock()
            client = service.vision_client
        mock_client.assert_called_once_with(api_key="my-key")
        assert client is mock_client.return_value

    def test_uses_vertexai_when_gcp_credentials(self):
        service = NanoBananaService(
            repo=MagicMock(),
            gcp_project_id="proj",
            gcp_location="us-east1",
        )
        with patch("ii_agent.content.slides.nano_banana.service.genai.Client") as mock_client:
            mock_client.return_value = MagicMock()
            client = service.vision_client
        mock_client.assert_called_once_with(vertexai=True, project="proj", location="us-east1")

    def test_caches_client_on_second_access(self):
        service = _make_service(gemini_api_key="key")
        with patch("ii_agent.content.slides.nano_banana.service.genai.Client") as mock_client:
            mock_client.return_value = MagicMock()
            c1 = service.vision_client
            c2 = service.vision_client
        assert mock_client.call_count == 1
        assert c1 is c2


# ---------------------------------------------------------------------------
# detect_components – guard clauses
# ---------------------------------------------------------------------------

class TestDetectComponents:
    @pytest.mark.asyncio
    async def test_returns_failure_response_on_exception(self):
        repo = MagicMock()
        repo.validate_session_access = AsyncMock()
        service = _make_service(repo=repo)
        request = DetectRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
            image_url="https://example.com/img.png",
        )
        with patch.object(service, "_run_detection", side_effect=RuntimeError("boom")):
            result = await service.detect_components(MagicMock(), user_id="u1", request=request)
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_returns_empty_components_when_none_detected(self):
        repo = MagicMock()
        repo.validate_session_access = AsyncMock()
        service = _make_service(repo=repo)
        request = DetectRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=2,
            image_url="https://example.com/img.png",
        )
        with patch.object(service, "_run_detection", return_value=([], 1280, 720)):
            result = await service.detect_components(MagicMock(), user_id="u1", request=request)
        assert result.success is True
        assert result.components == []
        assert result.overlay_html is None


# ---------------------------------------------------------------------------
# regenerate_slide – guard clauses
# ---------------------------------------------------------------------------

class TestRegenerateSlide:
    @pytest.mark.asyncio
    async def test_returns_failure_when_no_instructions(self):
        repo = MagicMock()
        repo.validate_session_access = AsyncMock()
        service = _make_service(repo=repo)
        request = RegenerateRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
            current_image_url="https://example.com/img.png",
            instructions=[],
        )
        result = await service.regenerate_slide(MagicMock(), user_id="u1", request=request)
        assert result.success is False
        assert "No instructions" in (result.error or "")

    @pytest.mark.asyncio
    async def test_returns_failure_on_exception(self):
        repo = MagicMock()
        repo.validate_session_access = AsyncMock()
        service = _make_service(repo=repo)
        request = RegenerateRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
            current_image_url="https://example.com/img.png",
            instructions=[_instruction(InstructionType.AI_MODIFY, "make it blue")],
        )
        with patch.object(service, "_run_regeneration", side_effect=RuntimeError("fail")):
            result = await service.regenerate_slide(MagicMock(), user_id="u1", request=request)
        assert result.success is False


# ---------------------------------------------------------------------------
# revert_to_version
# ---------------------------------------------------------------------------

class TestRevertToVersion:
    @pytest.mark.asyncio
    async def test_returns_failure_when_target_not_found(self):
        repo = MagicMock()
        repo.validate_session_access = AsyncMock()
        repo.get_version_by_id = AsyncMock(return_value=None)
        service = _make_service(repo=repo)
        request = RevertRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
            target_version_id="nonexistent",
        )
        result = await service.revert_to_version(MagicMock(), user_id="u1", request=request)
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_returns_failure_when_version_belongs_to_different_slide(self):
        target = MagicMock()
        target.session_id = "s1"
        target.presentation_name = "deck"
        target.slide_number = 99  # wrong slide
        target.image_url = "https://example.com/old.png"
        target.version = 1

        repo = MagicMock()
        repo.validate_session_access = AsyncMock()
        repo.get_version_by_id = AsyncMock(return_value=target)
        service = _make_service(repo=repo)
        request = RevertRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
            target_version_id="v-old",
        )
        result = await service.revert_to_version(MagicMock(), user_id="u1", request=request)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_successful_revert_creates_new_version(self):
        target = MagicMock()
        target.session_id = "s1"
        target.presentation_name = "deck"
        target.slide_number = 1
        target.image_url = "https://example.com/old.png"
        target.version = 1

        new_version = MagicMock()
        new_version.id = "new-v-id"

        repo = MagicMock()
        repo.validate_session_access = AsyncMock()
        repo.get_version_by_id = AsyncMock(return_value=target)
        repo.create_version = AsyncMock(return_value=new_version)
        repo.update_slide_content_image = AsyncMock()

        service = _make_service(repo=repo)
        request = RevertRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
            target_version_id="v-old",
        )
        result = await service.revert_to_version(MagicMock(), user_id="u1", request=request)
        assert result.success is True
        assert result.new_version_id == "new-v-id"


# ---------------------------------------------------------------------------
# _build_overlay_html
# ---------------------------------------------------------------------------

class TestBuildOverlayHtml:
    def test_returns_valid_html_string(self):
        service = _make_service()
        components = [_detected_component()]
        html = service._build_overlay_html(
            image_url="https://example.com/img.png",
            components=components,
            slide_number=1,
        )
        assert "<!DOCTYPE html>" in html
        assert "nano-banana-overlay" in html

    def test_escapes_image_url(self):
        service = _make_service()
        html = service._build_overlay_html(
            image_url="https://example.com/img?a=1&b=2",
            components=[],
            slide_number=1,
        )
        assert "&amp;" in html

    def test_includes_slide_number(self):
        service = _make_service()
        html = service._build_overlay_html(
            image_url="https://example.com/img.png",
            components=[],
            slide_number=7,
        )
        assert 'content="7"' in html or 'data-slide-number="7"' in html


# ---------------------------------------------------------------------------
# _build_component_div – static method
# ---------------------------------------------------------------------------

class TestBuildComponentDiv:
    def test_returns_div_with_design_id(self):
        comp = _detected_component(design_id="nano-title-0", component_type="title")
        div = NanoBananaService._build_component_div(
            comp=comp,
            slide_number=1,
            container_width=1280.0,
            container_height=720.0,
            display_width=1280.0,
            display_height=720.0,
            offset_left=0.0,
            offset_top=0.0,
        )
        assert 'data-design-id="nano-title-0"' in div

    def test_text_component_includes_text_fill_style(self):
        comp = _detected_component(component_type="title", text_content="My Title")
        div = NanoBananaService._build_component_div(
            comp=comp,
            slide_number=1,
            container_width=1280.0,
            container_height=720.0,
            display_width=1280.0,
            display_height=720.0,
            offset_left=0.0,
            offset_top=0.0,
        )
        assert "-webkit-text-fill-color" in div

    def test_non_text_component_has_empty_inner_html(self):
        comp = _detected_component(component_type="shape", text_content=None)
        div = NanoBananaService._build_component_div(
            comp=comp,
            slide_number=1,
            container_width=1280.0,
            container_height=720.0,
            display_width=1280.0,
            display_height=720.0,
            offset_left=0.0,
            offset_top=0.0,
        )
        # shape is not a text component
        assert "-webkit-text-fill-color" not in div


# ---------------------------------------------------------------------------
# _get_image_dimensions
# ---------------------------------------------------------------------------

class TestGetImageDimensions:
    def test_returns_correct_dimensions(self):
        from io import BytesIO
        from PIL import Image
        img = Image.new("RGB", (640, 480))
        buf = BytesIO()
        img.save(buf, format="PNG")
        dims = NanoBananaService._get_image_dimensions(buf.getvalue())
        assert dims == (640, 480)

    def test_returns_default_on_invalid_bytes(self):
        dims = NanoBananaService._get_image_dimensions(b"not_an_image")
        assert dims == (1280, 720)


# ---------------------------------------------------------------------------
# _extract_text_response
# ---------------------------------------------------------------------------

class TestExtractTextResponse:
    def test_extracts_text_from_response_parts(self):
        part = MagicMock()
        part.text = "hello world"
        candidate = MagicMock()
        candidate.content.parts = [part]
        response = MagicMock()
        response.candidates = [candidate]
        result = NanoBananaService._extract_text_response(response)
        assert result == "hello world"

    def test_returns_empty_string_when_no_candidates(self):
        response = MagicMock()
        response.candidates = []
        result = NanoBananaService._extract_text_response(response)
        assert result == ""

    def test_concatenates_multiple_parts(self):
        p1, p2 = MagicMock(), MagicMock()
        p1.text = "part1 "
        p2.text = "part2"
        candidate = MagicMock()
        candidate.content.parts = [p1, p2]
        response = MagicMock()
        response.candidates = [candidate]
        result = NanoBananaService._extract_text_response(response)
        assert result == "part1 part2"


# ---------------------------------------------------------------------------
# _parse_detection_response
# ---------------------------------------------------------------------------

class TestParseDetectionResponse:
    def test_returns_empty_list_for_empty_text(self):
        result = NanoBananaService._parse_detection_response("", 1280, 720)
        assert result == []

    def test_returns_empty_list_for_invalid_json(self):
        result = NanoBananaService._parse_detection_response("not json", 1280, 720)
        assert result == []

    def test_returns_empty_list_when_json_is_not_list(self):
        result = NanoBananaService._parse_detection_response('{"key": "val"}', 1280, 720)
        assert result == []

    def test_parses_valid_components(self):
        raw = [
            {
                "component_type": "title",
                "label": "Title",
                "bounding_box": {"left": 100, "top": 50, "width": 400, "height": 60},
                "z_index": 2,
                "confidence": 0.95,
            }
        ]
        import json
        result = NanoBananaService._parse_detection_response(json.dumps(raw), 1280, 720)
        assert len(result) == 1
        assert result[0].design_id == "nano-title-0"
        assert result[0].component_type == "title"

    def test_strips_markdown_code_blocks(self):
        import json
        raw = [{"component_type": "shape", "label": "Box", "bounding_box": {"left": 10, "top": 10, "width": 100, "height": 50}}]
        text = f"```json\n{json.dumps(raw)}\n```"
        result = NanoBananaService._parse_detection_response(text, 1280, 720)
        assert len(result) == 1

    def test_skips_components_with_invalid_bounding_box(self):
        import json
        raw = [
            {
                "component_type": "image",
                "label": "Img",
                "bounding_box": {"left": 0, "top": 0, "width": 0, "height": 0},
            }
        ]
        result = NanoBananaService._parse_detection_response(json.dumps(raw), 1280, 720)
        assert result == []


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

class TestModuleLevelHelpers:
    def test_parse_bounding_box_returns_none_for_non_dict(self):
        result = _parse_bounding_box("not a dict", 1280, 720)
        assert result is None

    def test_parse_bounding_box_uses_x_y_aliases(self):
        raw = {"x": 100, "y": 50, "width": 200, "height": 100}
        result = _parse_bounding_box(raw, 1280, 720)
        assert result is not None
        assert isinstance(result, BoundingBox)

    def test_parse_bounding_box_computes_from_right_bottom(self):
        raw = {"left": 100, "top": 50, "right": 300, "bottom": 150}
        result = _parse_bounding_box(raw, 1280, 720)
        assert result is not None
        assert result.width > 0

    def test_parse_bounding_box_returns_none_for_zero_size(self):
        raw = {"left": 0, "top": 0, "width": 0, "height": 0}
        result = _parse_bounding_box(raw, 1280, 720)
        assert result is None

    def test_parse_styles_returns_none_for_non_dict(self):
        result = _parse_styles("not a dict")
        assert result is None

    def test_parse_styles_returns_component_styles(self):
        raw = {"font_size": "16px", "color": "#fff"}
        result = _parse_styles(raw)
        assert isinstance(result, ComponentStyles)
        assert result.font_size == "16px"
        assert result.color == "#fff"

    def test_parse_styles_returns_none_for_none(self):
        result = _parse_styles(None)
        assert result is None

    def test_build_edit_summary_single_text_edit(self):
        inst = _instruction(InstructionType.TEXT_EDIT)
        result = _build_edit_summary([inst])
        assert result == "Text edit"

    def test_build_edit_summary_no_instructions(self):
        result = _build_edit_summary([])
        assert result == "No changes"

    def test_build_edit_summary_ai_modify_truncates_long_prompt(self):
        long_prompt = "A" * 100
        inst = _instruction(InstructionType.AI_MODIFY, ai_prompt=long_prompt)
        result = _build_edit_summary([inst])
        assert result.startswith("AI:")
        assert len(result) < len(long_prompt) + 10

    def test_build_edit_summary_multiple_instructions_joined(self):
        insts = [
            _instruction(InstructionType.TEXT_EDIT),
            _instruction(InstructionType.AI_MODIFY, "make red"),
        ]
        result = _build_edit_summary(insts)
        assert ", " in result

    def test_build_edit_summary_many_instructions_shows_count(self):
        insts = [_instruction(InstructionType.TEXT_EDIT) for _ in range(5)]
        result = _build_edit_summary(insts)
        assert "5" in result and "changes" in result

    def test_inject_runtime_script_with_head_tag(self):
        html = "<html><head></head><body></body></html>"
        result = _inject_runtime_script(html)
        assert "<head>" in result
        # Should inject something between head tags
        assert len(result) > len(html)

    def test_inject_runtime_script_with_html_tag_only(self):
        html = "<html><body></body></html>"
        result = _inject_runtime_script(html)
        assert "<head>" in result

    def test_inject_runtime_script_prepends_when_no_tags(self):
        html = "<div>bare div</div>"
        result = _inject_runtime_script(html)
        assert html in result

    def test_text_component_types_constant(self):
        assert "title" in TEXT_COMPONENT_TYPES
        assert "subtitle" in TEXT_COMPONENT_TYPES
        assert "footer" in TEXT_COMPONENT_TYPES

    # def test_vision_detection_model_constant(self):
    #     assert VISION_DETECTION_MODEL == "gemini-3-flash-preview"
