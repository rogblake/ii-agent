from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ii_agent.content.slides.nano_banana.schemas import (
    BoundingBox,
    ComponentStyles,
    DetectedComponent,
    DetectRequest,
    Instruction,
    InstructionType,
    RegenerateRequest,
    RemoveBackgroundRequest,
    RevertRequest,
    Selection,
    SelectionType,
)
from ii_agent.content.slides.nano_banana.service import (
    NanoBananaService,
    _build_edit_summary,
    _inject_runtime_script,
    _parse_bounding_box,
    _parse_styles,
)


class _FakeRepo:
    def __init__(self):
        self.validate_session_access = AsyncMock()
        self.create_version = AsyncMock(
            return_value=SimpleNamespace(id="ver-2", version=2)
        )
        self.update_slide_content_image = AsyncMock()
        self.get_slide = AsyncMock(return_value=None)
        self.get_versions = AsyncMock(return_value=[])
        self.get_version_by_id = AsyncMock(return_value=None)


def _service(repo: _FakeRepo) -> NanoBananaService:
    return NanoBananaService(repo=repo, gemini_api_key="test-key")


def _instruction_text() -> Instruction:
    return Instruction(
        id="i1",
        selection=Selection(type=SelectionType.COMPONENT, component_id="nano-title-0"),
        instruction_type=InstructionType.TEXT_EDIT,
        new_text="Updated",
        timestamp=1000,
    )


@pytest.mark.asyncio
async def test_detect_components_success(monkeypatch):
    repo = _FakeRepo()
    service = _service(repo)
    monkeypatch.setattr(
        service,
        "_run_detection",
        AsyncMock(return_value=([], 1280, 720)),
    )

    response = await service.detect_components(
        db=None,
        user_id="user-1",
        request=DetectRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
            image_url="https://example.com/img.png",
        ),
    )

    assert response.success is True
    assert response.slide_number == 1
    repo.validate_session_access.assert_awaited_once()


@pytest.mark.asyncio
async def test_detect_components_failure(monkeypatch):
    repo = _FakeRepo()
    service = _service(repo)
    monkeypatch.setattr(
        service,
        "_run_detection",
        AsyncMock(side_effect=RuntimeError("vision unavailable")),
    )

    response = await service.detect_components(
        db=None,
        user_id="user-1",
        request=DetectRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=2,
            image_url="https://example.com/img.png",
        ),
    )

    assert response.success is False
    assert "Detection failed" in (response.error or "")


@pytest.mark.asyncio
async def test_regenerate_slide_validation_and_failure(monkeypatch):
    repo = _FakeRepo()
    service = _service(repo)

    no_instructions = await service.regenerate_slide(
        db=None,
        user_id="u1",
        request=RegenerateRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
            current_image_url="https://example.com/a.png",
            instructions=[],
        ),
    )
    assert no_instructions.success is False
    assert no_instructions.error == "No instructions provided"

    monkeypatch.setattr(
        service,
        "_run_regeneration",
        AsyncMock(return_value={"success": False, "error": "model error"}),
    )
    failed = await service.regenerate_slide(
        db=None,
        user_id="u1",
        request=RegenerateRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
            current_image_url="https://example.com/a.png",
            instructions=[_instruction_text()],
        ),
    )
    assert failed.success is False
    assert failed.error == "model error"


@pytest.mark.asyncio
async def test_regenerate_slide_success(monkeypatch):
    repo = _FakeRepo()
    service = _service(repo)
    monkeypatch.setattr(
        service,
        "_run_regeneration",
        AsyncMock(return_value={"success": True, "url": "https://example.com/new.png"}),
    )

    response = await service.regenerate_slide(
        db=None,
        user_id="u1",
        request=RegenerateRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
            current_image_url="https://example.com/a.png",
            instructions=[_instruction_text()],
        ),
    )

    assert response.success is True
    assert response.new_image_url == "https://example.com/new.png"
    repo.create_version.assert_awaited_once()
    repo.update_slide_content_image.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_background_success_and_failure(monkeypatch):
    repo = _FakeRepo()
    service = _service(repo)

    monkeypatch.setattr(
        service,
        "_run_background_removal",
        AsyncMock(return_value={"success": False, "error": "bg failed"}),
    )
    failed = await service.remove_background(
        db=None,
        user_id="u1",
        request=RemoveBackgroundRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
            image_url="https://example.com/a.png",
        ),
    )
    assert failed.success is False
    assert failed.error == "bg failed"

    monkeypatch.setattr(
        service,
        "_run_background_removal",
        AsyncMock(return_value={"success": True, "url": "https://example.com/new.png"}),
    )
    success = await service.remove_background(
        db=None,
        user_id="u1",
        request=RemoveBackgroundRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
            image_url="https://example.com/a.png",
        ),
    )
    assert success.success is True
    assert success.new_version_id == "ver-2"


@pytest.mark.asyncio
async def test_get_versions_and_revert_paths():
    repo = _FakeRepo()
    repo.get_slide = AsyncMock(
        return_value=SimpleNamespace(
            slide_content='<img src="https://example.com/current.png" />'
        )
    )
    repo.get_versions = AsyncMock(
        return_value=[
            SimpleNamespace(
                id="v1",
                version=1,
                image_url="https://example.com/current.png",
                thumbnail_url=None,
                edit_summary="First",
                created_at=datetime.now(timezone.utc),
            )
        ]
    )
    repo.get_version_by_id = AsyncMock(
        return_value=SimpleNamespace(
            id="v1",
            version=1,
            image_url="https://example.com/current.png",
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
        )
    )
    service = _service(repo)

    versions = await service.get_versions(
        db=None,
        user_id="u1",
        session_id="s1",
        presentation_name="deck",
        slide_number=1,
    )
    assert len(versions.versions) == 1
    assert versions.current_version_id == "v1"

    reverted = await service.revert_to_version(
        db=None,
        user_id="u1",
        request=RevertRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
            target_version_id="v1",
        ),
    )
    assert reverted.success is True
    assert reverted.new_version_id == "ver-2"

    repo.get_version_by_id = AsyncMock(return_value=None)
    not_found = await service.revert_to_version(
        db=None,
        user_id="u1",
        request=RevertRequest(
            session_id="s1",
            presentation_name="deck",
            slide_number=1,
            target_version_id="missing",
        ),
    )
    assert not_found.success is False
    assert not_found.error == "Target version not found"


def test_parse_bounding_box_and_styles_helpers():
    bbox = _parse_bounding_box(
        {"left": 64, "top": 36, "width": 640, "height": 360},
        img_width=1280,
        img_height=720,
    )
    assert isinstance(bbox, BoundingBox)
    assert round(bbox.x, 2) == 5.0
    assert round(bbox.width, 2) == 50.0

    from_edges = _parse_bounding_box(
        {"x": 10, "y": 20, "right": 30, "bottom": 70},
        img_width=100,
        img_height=100,
    )
    assert isinstance(from_edges, BoundingBox)
    assert round(from_edges.width, 2) == 20.0
    assert round(from_edges.height, 2) == 50.0

    invalid = _parse_bounding_box({"left": 1, "top": 1, "width": 0, "height": 0}, 100, 100)
    assert invalid is None

    styles = _parse_styles({"font_size": "24px", "color": "#111"})
    assert isinstance(styles, ComponentStyles)
    assert styles.font_size == "24px"
    assert styles.color == "#111"
    assert _parse_styles(None) is None


def test_build_edit_summary_variants():
    one = _build_edit_summary([_instruction_text()])
    assert one == "Text edit"

    ai_inst = Instruction(
        id="i2",
        selection=Selection(type=SelectionType.SPOT, spot_x=10, spot_y=20),
        instruction_type=InstructionType.AI_MODIFY,
        ai_prompt="make this brighter and add contrast" * 4,
        timestamp=1001,
    )
    bg_inst = Instruction(
        id="i3",
        selection=Selection(type=SelectionType.BOX, box=BoundingBox(x=1, y=1, width=10, height=10)),
        instruction_type=InstructionType.REMOVE_BACKGROUND,
        timestamp=1002,
    )
    many = _build_edit_summary([_instruction_text(), ai_inst, bg_inst])
    assert "Text edit" in many
    assert "AI:" in many
    assert "Remove background" in many

    fallback = _build_edit_summary([])
    assert fallback == "No changes"


def test_inject_runtime_script_fallback_locations():
    with_head = _inject_runtime_script("<html><head></head><body>ok</body></html>")
    assert "__DESIGN_MODE_RUNTIME__" in with_head

    without_head = _inject_runtime_script("<html><body>ok</body></html>")
    assert "<head>" in without_head

    raw = _inject_runtime_script("<div>ok</div>")
    assert raw.startswith("<link") or "__DESIGN_MODE_RUNTIME__" in raw


def test_parse_detection_response_and_overlay_building(monkeypatch):
    repo = _FakeRepo()
    service = _service(repo)

    components = service._parse_detection_response(
        '[{"component_type":"title","label":"Title","text_content":"Hello","bounding_box":{"left":0,"top":0,"width":640,"height":120}}]',
        1280,
        720,
    )
    assert len(components) == 1
    assert components[0].design_id.startswith("nano-title-")

    bad_json = service._parse_detection_response("not-json", 1280, 720)
    assert bad_json == []

    not_list = service._parse_detection_response('{"a":1}', 1280, 720)
    assert not_list == []

    overlay = service._build_overlay_html(
        image_url="https://example.com/image.png",
        components=[
            DetectedComponent(
                design_id="nano-title-0",
                component_type="title",
                label="Title",
                text_content="Hello",
                bounding_box=BoundingBox(x=10, y=10, width=40, height=20),
                styles=ComponentStyles(font_size="24px", color="#000"),
            )
        ],
        slide_number=1,
        image_width=1280,
        image_height=720,
    )
    assert 'data-design-id="nano-title-0"' in overlay
    assert "__DESIGN_MODE_RUNTIME__" in overlay
