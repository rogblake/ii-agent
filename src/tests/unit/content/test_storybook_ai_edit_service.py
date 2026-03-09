"""Unit tests for ii_agent.content.storybook.ai_edit_service."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.content.storybook.ai_edit_service import (
    DEFAULT_TEXT_PERCENTAGE,
    StorybookAIEditService,
    _build_extension_prompt,
    _build_style_context,
    _calculate_safe_zones,
    _enhance_prompt_with_style,
    _extract_page,
    _extract_text_from_html,
    _extract_text_percentage_from_html,
    _extract_text_position_from_html,
    _get_optimal_aspect_ratio,
)
from ii_agent.chat.schemas import ImageURLContent, MessageRole, TextContent
from ii_agent.core.exceptions import ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service():
    return StorybookAIEditService(
        session_service=MagicMock(),
        user_service=MagicMock(),
        credit_service=MagicMock(),
        llm_setting_service=MagicMock(),
        llm_execution=MagicMock(),
        config=MagicMock(),
    )


def _storybook(
    *,
    id_: str = "sb-1",
    name: str = "My Story",
    session_id: str = "c8f8f5d8-ec9a-4b4c-b1d7-1234567890ab",
    aspect_ratio: str = "16:9",
    resolution: str = "1K",
    style_json: dict[str, Any] | None = None,
    pages: list[Any] | None = None,
):
    return SimpleNamespace(
        id=id_,
        name=name,
        session_id=session_id,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        style_json=style_json or {},
        pages=pages or [],
    )


def _llm_config_stub():
    model = SimpleNamespace(temperature=0.1, thinking_tokens=1)

    def _copy(deep: bool = True):
        model_copy = SimpleNamespace(temperature=model.temperature, thinking_tokens=model.thinking_tokens)
        return model_copy

    model.model_copy = _copy
    return model


# ---------------------------------------------------------------------------
# Extractor helpers
# ---------------------------------------------------------------------------


def test_build_extension_prompt_for_positions():
    assert "to the right" in _build_extension_prompt("Ref", "separate_page")
    assert "to the left" in _build_extension_prompt("Ref", "right")
    assert "to the right" in _build_extension_prompt("Ref", "left")
    assert "downward" in _build_extension_prompt("Ref", "top")
    assert "upward" in _build_extension_prompt("Ref", "bottom")
    assert "Generate an image" in _build_extension_prompt("Ref", None)


def test_build_style_context_adds_fields_and_skips_empty():
    assert _build_style_context({"character_description": "hero"}) == "Character: hero"
    assert _build_style_context({"art_style": "watercolor", "color_palette": "warm"}) == "Art style: watercolor. Color palette: warm"
    assert _build_style_context({"foo": "bar"}) == ""


def test_extract_text_from_html_extracts_editable_text():
    html = '<div data-editable="text">Hello</div><span data-editable="text">World</span>'
    assert _extract_text_from_html(html) == "Hello World"


def test_extract_text_position_and_percentage_parsers():
    assert _extract_text_position_from_html(
        ".storybook-page{ flex-direction: row; }"
    ) == "right"
    assert _extract_text_position_from_html(
        ""
    ) is None
    assert _extract_text_percentage_from_html(
        ".text-section { flex: 0 0 30%; }"
    ) == 30
    assert _extract_text_percentage_from_html(
        ".image-section { flex: 0 0 70%; }"
    ) == 30


def test_optimal_aspect_ratio_and_safe_zones():
    assert _get_optimal_aspect_ratio("16:9", "none", 0, None) == "16:9"
    assert _get_optimal_aspect_ratio("16:9", "right", 0, None) == "16:9"
    assert _get_optimal_aspect_ratio("16:9", "left", 25, "unknown") in {"1:1", "2:3", "3:2", "16:9", "21:9", "4:3", "3:4", "1.777"}
    assert _get_optimal_aspect_ratio("invalid", "left", 25, "gemini") == "invalid"

    assert _calculate_safe_zones("16:9", "16:9", "none", 0) == (100, 100)
    w, h = _calculate_safe_zones("16:9", "3:2", "right", 30)
    assert 0 < w <= 100
    assert h == 100


def test_extract_page_and_text_position_helpers():
    p1 = SimpleNamespace(page_number=1)
    p2 = SimpleNamespace(page_number=2)
    assert _extract_page(SimpleNamespace(pages=[p1, p2]), 2) is p2
    assert _extract_page(SimpleNamespace(pages=[p1]), 2) is None


# ---------------------------------------------------------------------------
# rewrite_content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rewrite_content_raises_for_blank_input():
    service = _make_service()
    with pytest.raises(ValidationError, match="No content provided"):
        await service.rewrite_content(
            db=MagicMock(),
            storybook=_storybook(),
            user_id="user-1",
            content="   ",
        )


@pytest.mark.asyncio
async def test_rewrite_content_success_and_with_image_url():
    service = _make_service()
    service._resolve_storybook_llm_config = AsyncMock(return_value=(_llm_config_stub(), "default"))

    user_client = MagicMock()
    user_client.new_message = MagicMock(side_effect=["msg1", "msg2"])
    user_client.send_once = AsyncMock(
        return_value=SimpleNamespace(
            content=[TextContent(text="rewritten text"), ImageURLContent(url="x")]
        )
    )
    service._llm_execution = user_client

    with patch_client():
        with patch(
            "ii_agent.content.storybook.ai_edit_service.get_client",
            return_value=user_client,
        ):
            result = await service.rewrite_content(
                db=MagicMock(),
                storybook=_storybook(),
                user_id="user-1",
                content="Original prompt",
                page_image_url="https://img",
            )

    assert result == "rewritten text"


@pytest.mark.asyncio
async def test_rewrite_content_raises_when_no_text_returned():
    service = _make_service()
    service._resolve_storybook_llm_config = AsyncMock(return_value=(_llm_config_stub(), "default"))

    user_client = MagicMock()
    user_client.new_message = MagicMock(side_effect=["msg1", "msg2"])
    user_client.send_once = AsyncMock(
        return_value=SimpleNamespace(
            content=[ImageURLContent(url="x")]
        )
    )
    service._llm_execution = user_client

    with patch_client():
        with patch(
            "ii_agent.content.storybook.ai_edit_service.get_client",
            return_value=user_client,
        ):
            with pytest.raises(ValidationError, match="did not return any rewritten content"):
                await service.rewrite_content(
                    db=MagicMock(),
                    storybook=_storybook(),
                    user_id="user-1",
                    content="Original prompt",
                )


# ---------------------------------------------------------------------------
# generate_background
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_background_rejects_blank_prompt():
    service = _make_service()
    with pytest.raises(ValidationError, match="No prompt"):
        await service.generate_background(
            db=MagicMock(),
            storybook=_storybook(),
            user_id="u1",
            prompt="",
        )


@pytest.mark.asyncio
async def test_generate_background_requires_api_key():
    service = _make_service()
    service._user_service.get_active_api_key = AsyncMock(return_value=None)
    with pytest.raises(ValidationError, match="No active API key"):
        await service.generate_background(
            db=MagicMock(),
            storybook=_storybook(),
            user_id="u1",
            prompt="A sunset",
        )


@pytest.mark.asyncio
async def test_generate_background_success_and_deducts_credits():
    service = _make_service()
    service._user_service.get_active_api_key = AsyncMock(return_value="api-key")
    service._deduct_image_credits = AsyncMock()

    with patch_generate_image({"url": "https://cdn/image.png", "cost": 0.05}):
        url = await service.generate_background(
            db=MagicMock(),
            storybook=_storybook(style_json={"image_provider": "gemini"}),
            user_id="u1",
            prompt="A tree",
            page_image_url="https://existing.png",
            text_position="left",
        )

    assert url == "https://cdn/image.png"
    service._deduct_image_credits.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_background_missing_image_url_raises():
    service = _make_service()
    service._user_service.get_active_api_key = AsyncMock(return_value="api-key")
    with patch_generate_image({"cost": 0.01}):
        with pytest.raises(RuntimeError, match="did not return an image URL"):
            await service.generate_background(
                db=MagicMock(),
                storybook=_storybook(),
                user_id="u1",
                prompt="A tree",
            )


# ---------------------------------------------------------------------------
# regenerate_image
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regenerate_image_raises_when_page_not_found():
    service = _make_service()
    with pytest.raises(ValidationError, match="Page not found"):
        await service.regenerate_image(
            db=MagicMock(),
            storybook=_storybook(pages=[]),
            user_id="u1",
            page_number=2,
            prompt="A scene",
        )


@pytest.mark.asyncio
async def test_regenerate_image_success_with_separate_page_and_next_text_page():
    page1 = SimpleNamespace(
        page_number=1,
        image_url="https://page1.png",
        html_content="",
        metadata={"is_separate_page_image": True},
    )
    page2 = SimpleNamespace(
        page_number=2,
        image_url="https://page2.png",
        html_content='<div data-editable="text">Scene follows from page one.</div>',
        metadata={"is_text_only_page": True, "linked_image_page": 1},
    )
    storybook = _storybook(pages=[page1, page2], style_json={"image_provider": "gemini"})

    service = _make_service()
    service._user_service.get_active_api_key = AsyncMock(return_value="api-key")
    service._deduct_image_credits = AsyncMock()

    with patch_generate_image({"url": "https://out.png", "cost": 0.02}):
        with patch("ii_agent.content.storybook.ai_edit_service._generate_image", AsyncMock(return_value={"url": "https://out.png", "cost": 0.02})):
            result = await service.regenerate_image(
                db=MagicMock(),
                storybook=storybook,
                user_id="u1",
                page_number=1,
                prompt="Paint the same scene",
            )

    assert result == "https://out.png"


@pytest.mark.asyncio
async def test_regenerate_image_retries_and_raises_after_failures():
    page = SimpleNamespace(
        page_number=1,
        image_url="https://page1.png",
        html_content="",
        metadata={},
    )
    storybook = _storybook(pages=[page], style_json={"image_provider": "gemini"})

    service = _make_service()
    service._user_service.get_active_api_key = AsyncMock(return_value="api-key")
    service._deduct_image_credits = AsyncMock()

    with patch("ii_agent.content.storybook.ai_edit_service._generate_image", AsyncMock(side_effect=RuntimeError("boom"))):
        with patch("ii_agent.content.storybook.ai_edit_service.asyncio.sleep", AsyncMock()):
            with pytest.raises(RuntimeError, match="Failed to regenerate image after 5 attempts"):
                await service.regenerate_image(
                    db=MagicMock(),
                    storybook=storybook,
                    user_id="u1",
                    page_number=1,
                    prompt="Paint",
                )


# ---------------------------------------------------------------------------
# _resolve_storybook_llm_config and _deduct_image_credits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_storybook_llm_config_invalid_session_and_valid_setting():
    service = _make_service()
    fallback = SimpleNamespace(model_copy=MagicMock(return_value="fallback_copy"))
    setting = SimpleNamespace(model_copy=MagicMock(return_value="setting_copy"))

    with patch(
        "ii_agent.content.storybook.ai_edit_service.get_system_llm_config",
        return_value=fallback,
    ):
        config, model_id = await service._resolve_storybook_llm_config(
            db=MagicMock(),
            user_id="u1",
            session_id="bad-uuid",
        )
        assert config == "fallback_copy"
        assert model_id == "default"

    service._session_service.get_session_by_id = AsyncMock(return_value=SimpleNamespace(llm_setting_id="m1"))
    service._llm_setting_service.get_user_llm_config = AsyncMock(return_value=setting)

    with patch(
        "ii_agent.content.storybook.ai_edit_service.get_system_llm_config",
        return_value=fallback,
    ):
        config, model_id = await service._resolve_storybook_llm_config(
            db=MagicMock(),
            user_id="u1",
            session_id="b9f3f6e8-12ad-4dd2-b4c0-8b9c9b0f3cf2",
        )
        assert config == "setting_copy"
        assert model_id == "m1"


@pytest.mark.asyncio
async def test_deduct_image_credits_no_cost_skips_service():
    service = _make_service()
    service._credit_service.deduct_and_track_session_usage = AsyncMock()
    await service._deduct_image_credits(
        db=MagicMock(),
        user_id="u1",
        session_id="s1",
        raw_cost=None,
        context="ctx",
    )
    service._credit_service.deduct_and_track_session_usage.assert_awaited_once()

    await service._deduct_image_credits(
        db=MagicMock(),
        user_id="u1",
        session_id="s1",
        raw_cost=-0.5,
        context="ctx",
    )
    assert service._credit_service.deduct_and_track_session_usage.await_count == 1


@pytest.mark.asyncio
async def test_deduct_image_credits_tracks_when_service_says_no_funds():
    service = _make_service()
    service._credit_service.deduct_and_track_session_usage = AsyncMock(return_value=False)
    await service._deduct_image_credits(
        db=MagicMock(),
        user_id="u1",
        session_id="s1",
        raw_cost=0.5,
        context="ctx",
    )
    service._credit_service.deduct_and_track_session_usage.assert_awaited_once()


# ---------------------------------------------------------------------------
# Small context managers used above
# ---------------------------------------------------------------------------


class _PatchImageContext:
    def __init__(self, result):
        self._result = result

    def __enter__(self):
        self._patch = patch(
            "ii_agent.content.storybook.ai_edit_service._generate_image",
            AsyncMock(return_value=self._result),
        )
        self._patch.__enter__()
        return self._patch

    def __exit__(self, exc_type, exc, tb):
        self._patch.__exit__(exc_type, exc, tb)
        return False


def patch_generate_image(result):
    return _PatchImageContext(result)


def patch_client():
    return patch("ii_agent.content.storybook.ai_edit_service.get_client", lambda cfg: MagicMock())
