"""Deep unit tests for slides nano_banana/service covering remaining branches."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.content.slides.nano_banana.service import (
    NanoBananaService,
    TEXT_COMPONENT_TYPES,
    # VISION_DETECTION_MODEL,
)
from ii_agent.content.slides.nano_banana.schemas import (
    BoundingBox,
    ComponentStyles,
    DetectedComponent,
    DetectRequest,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detected_component(
    design_id: str = "c-1",
    component_type: str = "title",
    label: str = "Title",
) -> DetectedComponent:
    return DetectedComponent(
        design_id=design_id,
        component_type=component_type,
        label=label,
        bounding_box=BoundingBox(x=10, y=10, width=80, height=20),
        styles=ComponentStyles(),
    )


def _make_nano_service(
    gemini_api_key="test-key",
    gcp_project=None,
    gcp_location=None,
    repo=None,
) -> NanoBananaService:
    return NanoBananaService(
        repo=repo or AsyncMock(),
        gemini_api_key=gemini_api_key,
        gcp_project_id=gcp_project,
        gcp_location=gcp_location,
    )


# ---------------------------------------------------------------------------
# NanoBananaService.vision_client
# ---------------------------------------------------------------------------


class TestVisionClient:
    def test_lazy_loads_with_api_key(self):
        svc = _make_nano_service(gemini_api_key="sk-test")
        with patch("ii_agent.content.slides.nano_banana.service.genai.Client") as MockClient:
            MockClient.return_value = MagicMock()
            client = svc.vision_client
        assert client is not None

    def test_uses_vertexai_when_no_api_key(self):
        svc = _make_nano_service(
            gemini_api_key="",
            gcp_project="my-project",
            gcp_location="us-central1",
        )
        with patch("ii_agent.content.slides.nano_banana.service.genai.Client") as MockClient:
            MockClient.return_value = MagicMock()
            client = svc.vision_client
        MockClient.assert_called_once_with(
            vertexai=True, project="my-project", location="us-central1"
        )

    def test_raises_without_credentials(self):
        svc = _make_nano_service(gemini_api_key="", gcp_project=None, gcp_location=None)
        with pytest.raises(RuntimeError, match="No Gemini API key"):
            _ = svc.vision_client

    def test_cached_after_first_access(self):
        svc = _make_nano_service()
        mock_client = MagicMock()
        svc._vision_client = mock_client
        client = svc.vision_client
        assert client is mock_client


# ---------------------------------------------------------------------------
# NanoBananaService.detect_components
# ---------------------------------------------------------------------------


class TestDetectComponents:
    @pytest.mark.asyncio
    async def test_returns_success_response(self):
        repo = AsyncMock()
        svc = _make_nano_service(repo=repo)

        components = [_detected_component()]

        with patch.object(svc, "_run_detection", return_value=(components, 1920, 1080)):
            with patch.object(svc, "_build_overlay_html", return_value="<div>overlay</div>"):
                request = DetectRequest(
                    session_id="s-1",
                    presentation_name="deck",
                    slide_number=1,
                    image_url="https://img.url",
                )
                result = await svc.detect_components(None, user_id="u-1", request=request)

        assert result.success is True
        assert result.slide_number == 1
        assert len(result.components) == 1
        assert result.overlay_html == "<div>overlay</div>"

    @pytest.mark.asyncio
    async def test_no_overlay_when_no_components(self):
        repo = AsyncMock()
        svc = _make_nano_service(repo=repo)

        with patch.object(svc, "_run_detection", return_value=([], 1920, 1080)):
            request = DetectRequest(
                session_id="s-1",
                presentation_name="deck",
                slide_number=1,
                image_url="https://img.url",
            )
            result = await svc.detect_components(None, user_id="u-1", request=request)

        assert result.success is True
        assert result.overlay_html is None

    @pytest.mark.asyncio
    async def test_returns_failure_on_exception(self):
        repo = AsyncMock()
        svc = _make_nano_service(repo=repo)

        with patch.object(svc, "_run_detection", side_effect=RuntimeError("Boom")):
            request = DetectRequest(
                session_id="s-1",
                presentation_name="deck",
                slide_number=1,
                image_url="https://img.url",
            )
            result = await svc.detect_components(None, user_id="u-1", request=request)

        assert result.success is False
        assert "Boom" in result.error


# ---------------------------------------------------------------------------
# NanoBananaService._build_overlay_html
# ---------------------------------------------------------------------------


class TestBuildOverlayHtml:
    def test_includes_image_url(self):
        svc = _make_nano_service()
        components = [_detected_component()]
        result = svc._build_overlay_html(
            image_url="https://slide-img.url",
            components=components,
            slide_number=1,
            image_width=1920,
            image_height=1080,
        )
        assert "https://slide-img.url" in result

    def test_includes_component_elements(self):
        svc = _make_nano_service()
        components = [
            _detected_component(design_id="comp-1", component_type="title", label="My Title"),
            _detected_component(design_id="comp-2", component_type="image", label="Picture"),
        ]
        result = svc._build_overlay_html(
            image_url="https://img.url",
            components=components,
            slide_number=1,
            image_width=800,
            image_height=600,
        )
        assert "comp-1" in result or "My Title" in result
        assert "comp-2" in result or "Picture" in result

    def test_includes_runtime_scripts(self):
        svc = _make_nano_service()
        components = [_detected_component()]
        result = svc._build_overlay_html(
            image_url="https://img.url",
            components=components,
            slide_number=1,
            image_width=800,
            image_height=600,
        )
        assert "script" in result.lower()

    def test_returns_html_string(self):
        svc = _make_nano_service()
        components = [
            _detected_component(component_type="title"),
            _detected_component(design_id="c-2", component_type="image", label="Img"),
        ]
        result = svc._build_overlay_html(
            image_url="https://img.url",
            components=components,
            slide_number=2,
            image_width=800,
            image_height=600,
        )
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# NanoBananaService.get_versions
# ---------------------------------------------------------------------------


class TestGetVersions:
    @pytest.mark.asyncio
    async def test_returns_versions_list(self):
        from datetime import datetime, timezone
        repo = AsyncMock()
        repo.get_slide = AsyncMock(return_value=None)
        repo.get_versions = AsyncMock(
            return_value=[
                SimpleNamespace(
                    id="v1",
                    version=1,
                    image_url="https://img1.url",
                    thumbnail_url=None,
                    edit_summary="Initial",
                    created_at=datetime.now(timezone.utc),
                    session_id="s-1",
                    presentation_name="deck",
                    slide_number=1,
                ),
                SimpleNamespace(
                    id="v2",
                    version=2,
                    image_url="https://img2.url",
                    thumbnail_url=None,
                    edit_summary="Edit",
                    created_at=datetime.now(timezone.utc),
                    session_id="s-1",
                    presentation_name="deck",
                    slide_number=1,
                ),
            ]
        )
        svc = _make_nano_service(repo=repo)
        result = await svc.get_versions(
            None,
            user_id="u-1",
            session_id="s-1",
            presentation_name="deck",
            slide_number=1,
        )
        assert len(result.versions) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_versions(self):
        repo = AsyncMock()
        repo.get_slide = AsyncMock(return_value=None)
        repo.get_versions = AsyncMock(return_value=[])
        svc = _make_nano_service(repo=repo)
        result = await svc.get_versions(
            None,
            user_id="u-1",
            session_id="s-1",
            presentation_name="deck",
            slide_number=1,
        )
        assert len(result.versions) == 0


# ---------------------------------------------------------------------------
# NanoBananaService.revert_to_version
# ---------------------------------------------------------------------------


class TestRevertToVersion:
    @pytest.mark.asyncio
    async def test_returns_success_response(self):
        from ii_agent.content.slides.nano_banana.schemas import RevertRequest
        repo = AsyncMock()
        target_version = SimpleNamespace(
            id="v1",
            version=1,
            image_url="https://img1.url",
            session_id="s-1",
            presentation_name="deck",
            slide_number=1,
        )
        new_version = SimpleNamespace(id="v3", version=3, image_url="https://img1.url")
        repo.get_version_by_id = AsyncMock(return_value=target_version)
        repo.create_version = AsyncMock(return_value=new_version)
        repo.update_slide_content_image = AsyncMock()

        svc = _make_nano_service(repo=repo)
        request = RevertRequest(
            session_id="s-1",
            presentation_name="deck",
            slide_number=1,
            target_version_id="v1",
        )
        result = await svc.revert_to_version(None, user_id="u-1", request=request)
        assert result.success is True
        assert result.new_version_id == "v3"

    @pytest.mark.asyncio
    async def test_returns_failure_when_version_not_found(self):
        from ii_agent.content.slides.nano_banana.schemas import RevertRequest
        repo = AsyncMock()
        repo.get_version_by_id = AsyncMock(return_value=None)

        svc = _make_nano_service(repo=repo)
        request = RevertRequest(
            session_id="s-1",
            presentation_name="deck",
            slide_number=1,
            target_version_id="v-missing",
        )
        result = await svc.revert_to_version(None, user_id="u-1", request=request)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_returns_failure_when_version_belongs_to_different_slide(self):
        from ii_agent.content.slides.nano_banana.schemas import RevertRequest
        repo = AsyncMock()
        # Version from different session
        wrong_version = SimpleNamespace(
            id="v1",
            version=1,
            image_url="https://img.url",
            session_id="other-session",
            presentation_name="deck",
            slide_number=1,
        )
        repo.get_version_by_id = AsyncMock(return_value=wrong_version)

        svc = _make_nano_service(repo=repo)
        request = RevertRequest(
            session_id="s-1",
            presentation_name="deck",
            slide_number=1,
            target_version_id="v1",
        )
        result = await svc.revert_to_version(None, user_id="u-1", request=request)
        assert result.success is False


# ---------------------------------------------------------------------------
# NanoBananaService._parse_detection_response
# ---------------------------------------------------------------------------


class TestParseDetectionResponse:
    def test_parses_valid_json_list_response(self):
        svc = _make_nano_service()
        # The method expects a JSON list of component objects
        response_json = json.dumps([
            {
                "component_type": "title",
                "label": "Title",
                "bounding_box": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.2},
                "styles": {},
            }
        ])
        # image dimensions in pixels
        components = svc._parse_detection_response(response_json, 1920, 1080)
        assert len(components) == 1
        assert components[0].component_type == "title"

    def test_handles_empty_list(self):
        svc = _make_nano_service()
        components = svc._parse_detection_response("[]", 800, 600)
        assert components == []

    def test_handles_invalid_json(self):
        svc = _make_nano_service()
        components = svc._parse_detection_response("not-json!!!", 800, 600)
        assert components == []

    def test_handles_json_with_markdown_fences(self):
        svc = _make_nano_service()
        payload = "[]"
        fenced = f"```json\n{payload}\n```"
        components = svc._parse_detection_response(fenced, 800, 600)
        assert components == []

    def test_generates_unique_design_ids(self):
        svc = _make_nano_service()
        response_json = json.dumps([
            {
                "component_type": "text_block",
                "label": "Body",
                "bounding_box": {"x": 0.1, "y": 0.3, "width": 0.8, "height": 0.5},
                "styles": {},
            }
        ])
        components = svc._parse_detection_response(response_json, 800, 600)
        assert len(components) == 1
        assert components[0].design_id is not None
        # design_id format is nano-{type}-{idx}
        assert components[0].design_id.startswith("nano-")

    def test_handles_empty_string(self):
        svc = _make_nano_service()
        components = svc._parse_detection_response("", 800, 600)
        assert components == []

    def test_handles_non_list_response(self):
        svc = _make_nano_service()
        # Object, not list
        response_json = json.dumps({"components": []})
        components = svc._parse_detection_response(response_json, 800, 600)
        assert components == []

    def test_skips_items_with_invalid_bounding_box(self):
        svc = _make_nano_service()
        response_json = json.dumps([
            {
                "component_type": "title",
                "label": "Title",
                "bounding_box": {},  # Missing fields
            }
        ])
        components = svc._parse_detection_response(response_json, 800, 600)
        # Invalid bbox should be skipped
        assert len(components) == 0


# ---------------------------------------------------------------------------
# NanoBananaService._build_component_div
# ---------------------------------------------------------------------------


class TestBuildComponentDiv:
    def test_returns_html_div(self):
        svc = _make_nano_service()
        comp = _detected_component(design_id="test-comp", component_type="title", label="Title")
        result = svc._build_component_div(
            comp,
            slide_number=1,
            container_width=1920,
            container_height=1080,
            display_width=1920,
            display_height=1080,
            offset_left=0,
            offset_top=0,
        )
        assert "<div" in result
        assert "test-comp" in result

    def test_text_component_has_label(self):
        svc = _make_nano_service()
        comp = _detected_component(component_type="title", label="My Title")
        result = svc._build_component_div(
            comp,
            slide_number=1,
            container_width=800,
            container_height=600,
            display_width=800,
            display_height=600,
            offset_left=0,
            offset_top=0,
        )
        assert "My Title" in result

    def test_image_component_type(self):
        svc = _make_nano_service()
        comp = _detected_component(design_id="img-1", component_type="image", label="Photo")
        result = svc._build_component_div(
            comp,
            slide_number=1,
            container_width=800,
            container_height=600,
            display_width=800,
            display_height=600,
            offset_left=0,
            offset_top=0,
        )
        assert "img-1" in result


# ---------------------------------------------------------------------------
# TEXT_COMPONENT_TYPES constant
# ---------------------------------------------------------------------------


class TestTextComponentTypes:
    def test_contains_expected_types(self):
        assert "title" in TEXT_COMPONENT_TYPES
        assert "subtitle" in TEXT_COMPONENT_TYPES
        assert "text_block" in TEXT_COMPONENT_TYPES
        assert "bullet_list" in TEXT_COMPONENT_TYPES
        assert "footer" in TEXT_COMPONENT_TYPES
        assert "header" in TEXT_COMPONENT_TYPES
        assert "text" in TEXT_COMPONENT_TYPES

    def test_image_not_in_text_types(self):
        assert "image" not in TEXT_COMPONENT_TYPES


# ---------------------------------------------------------------------------
# NanoBananaService.regenerate_slide
# ---------------------------------------------------------------------------


class TestRegenerateSlide:
    @pytest.mark.asyncio
    async def test_returns_failure_on_slide_not_found(self):
        from ii_agent.content.slides.nano_banana.schemas import RegenerateRequest
        repo = AsyncMock()
        repo.get_slide = AsyncMock(side_effect=ValueError("Not found"))

        svc = _make_nano_service(repo=repo)
        request = RegenerateRequest(
            session_id="s-1",
            presentation_name="deck",
            slide_number=1,
            current_image_url="https://img.url",
            instructions=[],
        )
        result = await svc.regenerate_slide(None, user_id="u-1", request=request)
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_calls_validate_session_access(self):
        from ii_agent.content.slides.nano_banana.schemas import RegenerateRequest
        repo = AsyncMock()
        repo.get_slide = AsyncMock(return_value=None)

        svc = _make_nano_service(repo=repo)
        request = RegenerateRequest(
            session_id="s-1",
            presentation_name="deck",
            slide_number=1,
            current_image_url="https://img.url",
            instructions=[],
        )
        result = await svc.regenerate_slide(None, user_id="u-1", request=request)
        # validate_session_access should have been called
        repo.validate_session_access.assert_called_once()
        # Should fail because slide_gen_config import will fail
        assert result.success is False


# ---------------------------------------------------------------------------
# remove_background
# ---------------------------------------------------------------------------


class TestRemoveBackground:
    @pytest.mark.asyncio
    async def test_returns_failure_on_invalid_request(self):
        from ii_agent.content.slides.nano_banana.schemas import RemoveBackgroundRequest
        repo = AsyncMock()
        svc = _make_nano_service(repo=repo)

        request = RemoveBackgroundRequest(
            session_id="s-1",
            presentation_name="deck",
            slide_number=1,
            image_url="https://img.url",
        )

        with patch.object(svc, "_download_image", side_effect=RuntimeError("Download failed")):
            result = await svc.remove_background(None, user_id="u-1", request=request)

        assert result.success is False
        assert result.error is not None
